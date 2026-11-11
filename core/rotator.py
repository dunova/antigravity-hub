#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/rotator.py - Antigravity 5 小时配额看门狗与瀑布级联轮转守护进程
===================================================================
核心功能：
1. 5小时滑动桶实时守护与短板感知；
2. 级联瀑布选号算法：多维综合打分，优先使用健康高配额候选；
3. 人工干预保护锁 (Manual Override Lock)：尊重用户手动指定的账号，锁定期内绝不夺权；
4. 429 限流主动嗅探与智能避让；
5. 自动串联物理钥匙串热切号与 Teamwork 零 UI 断点接力。
"""

import os
import sys
import time
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

from .switcher import (
    AntigravityPhysicalManager,
    BASE_DATA_DIR,
    MANUAL_OVERRIDE_LOCK_PATH,
    _safe_float
)
from .recovery import AntigravitySessionRecoveryManager

logger = logging.getLogger("QuotaRotator")

EXHAUSTED_EPS = 0.0001       # 彻底耗尽物理门禁 (<= 0.01% -> 0%)
MIN_USABLE_WEEKLY = 0.005    # < 0.5% 四舍五入显示 0%，严禁自动选中
HEALTHY_WEEKLY_MIN = 0.015   # >= 1.5% 四舍五入 >= 2%，隔离 1% 周额度账号
HEALTHY_5H_MIN = 0.015       # >= 1.5% 四舍五入 >= 2%，避免残丝 5h 抢占健康候选


def _has_usable_refresh_token(acc: Dict[str, Any]) -> bool:
    """若账号明确声明 token/refresh_token 字段则校验其非空；无字段的合成测试对象默认放行"""
    if not isinstance(acc, dict):
        return False
    if "refresh_token" not in acc and "token" not in acc:
        return True
    tok = acc.get("token")
    rt = acc.get("refresh_token") or (tok.get("refresh_token") if isinstance(tok, dict) else "")
    return bool(str(rt or "").strip())


class AntigravityQuotaRotator:
    """配额看门狗与自动轮转守护进程"""

    def __init__(
        self,
        check_interval: int = 10,
        depletion_threshold: float = 0.0,
        data_dir: str = BASE_DATA_DIR
    ):
        self.check_interval = check_interval
        self.depletion_threshold = depletion_threshold
        self.data_dir = data_dir
        self.switcher = AntigravityPhysicalManager(data_dir=self.data_dir)
        self.recovery = AntigravitySessionRecoveryManager()
        self.exhausted_cooldown_map: Dict[str, float] = {}
        self.last_full_refresh_ts: float = 0.0

    def _load_runtime_settings(self) -> Tuple[str, float, str]:
        """读取轮换模式、对应模型告急阈值与自动选号策略（与 hub_settings.json / auto_rotation_config.json 保持一致）"""
        rot_mode = "gemini"
        rot_cfg_path = os.path.join(self.data_dir, "auto_rotation_config.json")
        if os.path.isfile(rot_cfg_path):
            try:
                with open(rot_cfg_path, "r", encoding="utf-8") as f:
                    raw_rot = json.load(f)
                if isinstance(raw_rot, dict):
                    m = raw_rot.get("mode")
                    if m in ("gemini", "claude", "off"):
                        rot_mode = m
                    elif not raw_rot.get("enabled", True):
                        rot_mode = "off"
                    elif raw_rot.get("policy") in ("claude_first", "claude"):
                        rot_mode = "claude"
            except Exception as ex:
                logger.debug(f"读取 auto_rotation_config.json 异常: {ex}")

        thresh = _safe_float(self.depletion_threshold, 0.0)
        strategy = "highest-quota"
        settings_path = os.path.join(self.data_dir, "data", "hub_settings.json")
        if not os.path.isfile(settings_path):
            alt_path = os.path.join(self.data_dir, "hub_settings.json")
            if os.path.isfile(alt_path):
                settings_path = alt_path
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    hub_cfg = json.load(f)
                if isinstance(hub_cfg, dict):
                    strategy = str(hub_cfg.get("rotation_strategy") or "highest-quota").strip() or "highest-quota"
                    if rot_mode == "claude":
                        thresh = _safe_float(hub_cfg.get("claude_threshold", thresh), thresh)
                    else:
                        thresh = _safe_float(hub_cfg.get("gemini_threshold", thresh), thresh)
            except Exception as ex:
                logger.debug(f"读取 hub_settings.json 异常: {ex}")

        return rot_mode, max(0.0, thresh), strategy

    def get_manual_lock(self) -> Optional[Dict[str, Any]]:
        """检查是否存在有效的人工干预保护锁"""
        lock_path = os.path.join(self.data_dir, "manual_override_lock.json")
        if not os.path.exists(lock_path):
            if self.data_dir == BASE_DATA_DIR and os.path.exists(MANUAL_OVERRIDE_LOCK_PATH):
                lock_path = MANUAL_OVERRIDE_LOCK_PATH
            else:
                return None
        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("locked_until", 0) > time.time():
                return data
            return None
        except Exception:
            return None

    def pick_best_standby_account(
        self,
        accounts: Dict[str, Any],
        current_email: str,
        rot_mode: str = "gemini",
        depletion_thresh: Optional[float] = None,
        strategy: str = "highest-quota",
        accounts_order: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        两级隔离瀑布选号算法（兼容 highest-quota / round-robin / least-used / sticky）：
        1. 硬性过滤：当前账号、30m 冷却期、风控锁定(validation_blocked)、禁用(disabled)、无可用 refresh_token、
           以及 5h <= 0.0001 或 周额度 < 0.005（四舍五入显示 0% 周耗尽）的账号；
        2. 分级隔离池：
           - Tier 0 (主力健康池): 周额度 >= 1.5% (显示 >= 2%) 且 5h >= 1.5%，且超过告急阈值；
           - Tier 1 (次健康池):   周额度 >= 1.5% 且 5h >= 1.5%（低于软阈值但未到 1% 残丝）；
           - Tier 2 (1% 残丝兜底池): 仅剩 0.5%~1.49% (1%) 周额度或极低 5h 残丝时才最后动用；
           只要存在任何 Tier 0/1 账号，1% 周额度账号绝不参与任何策略选号竞争；
        3. 在选定层级内严格按 rotation_strategy 挑选下一接力账号。
        """
        now_ts = time.time()
        thresh = _safe_float(
            self.depletion_threshold if depletion_thresh is None else depletion_thresh,
            0.0,
        )
        bucket_key = "claude" if rot_mode == "claude" else "gemini"

        candidates: List[Dict[str, Any]] = []
        for email, acc in accounts.items():
            if not isinstance(acc, dict) or email == current_email:
                continue

            if self.exhausted_cooldown_map.get(email, 0) > now_ts:
                continue

            if acc.get("validation_blocked") or acc.get("disabled"):
                continue

            if not _has_usable_refresh_token(acc):
                continue

            quota_info = acc.get(bucket_key) or {}
            k_5h = _safe_float(quota_info.get("quota_5h", 1.0), 1.0)
            k_wk = _safe_float(quota_info.get("quota_weekly", 1.0), 1.0)

            # 周耗尽短路 & 0% (<0.5%) 残余屏蔽
            if k_wk <= EXHAUSTED_EPS:
                k_5h = 0.0
            if k_5h <= EXHAUSTED_EPS or k_wk < MIN_USABLE_WEEKLY:
                continue

            prio_raw = acc.get("priority")
            priority = 999 if prio_raw is None else int(_safe_float(prio_raw, 999))
            last_used = int(_safe_float(acc.get("last_used_time") or acc.get("last_switched_at") or 0, 0))
            eff_quota = min(k_5h, k_wk)

            is_healthy_reserves = (k_wk >= HEALTHY_WEEKLY_MIN and k_5h >= HEALTHY_5H_MIN)
            if is_healthy_reserves and (thresh <= EXHAUSTED_EPS or eff_quota > thresh):
                tier = 0
            elif is_healthy_reserves:
                tier = 1
            else:
                tier = 2

            candidates.append({
                "email": email,
                "tier": tier,
                "priority": priority,
                "eff_quota": eff_quota,
                "k_5h": k_5h,
                "k_wk": k_wk,
                "last_used": last_used,
            })

        if not candidates:
            return None

        best_tier = min(c["tier"] for c in candidates)
        pool = [c for c in candidates if c["tier"] == best_tier]
        if best_tier == 2:
            logger.info("⚠️ [残丝兜底选号] 全池无 >=2% 健康账号，仅剩 1% 低额度池进入最终兜底挑选")

        if strategy == "round-robin":
            pool_emails = {c["email"] for c in pool}
            full_order: List[str] = []
            seen_lower = set()
            key_by_lower = {k.lower(): k for k in accounts.keys()}
            for em in (accounts_order or list(accounts.keys())):
                em_s = str(em).strip()
                if not em_s:
                    continue
                real_key = em_s if em_s in accounts else key_by_lower.get(em_s.lower())
                if real_key and real_key.lower() not in seen_lower:
                    full_order.append(real_key)
                    seen_lower.add(real_key.lower())
            for k in accounts.keys():
                if k.lower() not in seen_lower:
                    full_order.append(k)
                    seen_lower.add(k.lower())

            if current_email in full_order:
                start_idx = (full_order.index(current_email) + 1) % len(full_order)
            else:
                cur_low = (current_email or "").lower()
                low_list = [x.lower() for x in full_order]
                start_idx = ((low_list.index(cur_low) + 1) % len(full_order)) if cur_low in low_list else 0

            for offset in range(len(full_order)):
                candidate_email = full_order[(start_idx + offset) % len(full_order)]
                if candidate_email in pool_emails:
                    return candidate_email

        if strategy == "least-used":
            pool.sort(
                key=lambda c: (
                    c["last_used"],
                    c["priority"],
                    -round(c["eff_quota"], 6),
                    -round(c["k_wk"], 6),
                    -round(c["k_5h"], 6),
                )
            )
            return pool[0]["email"]

        # highest-quota / sticky / 默认：按 priority 与有效可用配额 min(5h, wk) 优先
        pool.sort(
            key=lambda c: (
                c["priority"],
                -round(c["eff_quota"], 6),
                -round(c["k_wk"], 6),
                -round(c["k_5h"], 6),
            )
        )
        return pool[0]["email"]

    def check_and_rotate_once(self) -> bool:
        """执行单次配额检查与必要时的自动轮换 (支持毫秒级本地LS状态嗅探 + 两级隔离瀑布无缝接力)"""
        rot_mode, depletion_thresh, rot_strategy = self._load_runtime_settings()
        if rot_mode == "off":
            return False

        ENGINE = None
        if self.data_dir == BASE_DATA_DIR:
            try:
                from hub.server import ENGINE as _LIVE_ENGINE
                ENGINE = _LIVE_ENGINE
            except Exception:
                ENGINE = None

        if ENGINE is not None:
            hub_data = ENGINE.load_accounts()
        else:
            hub_data = self.switcher.load_hub_accounts()

        accounts = hub_data.get("accounts", {})
        active_email = hub_data.get("active_email", "")

        if not active_email or active_email not in accounts:
            return False

        # 1. 优先从运行中的本地 language_server 实时同步当前活跃账号配额 (毫秒级响应，0网络开销)
        if ENGINE is not None:
            ENGINE.sync_from_local_language_server(hub_data)
            now_ts = time.time()
            if now_ts - self.last_full_refresh_ts >= 60.0:
                active_acc = accounts[active_email]
                ok_ref = ENGINE.refresh_single_account_quota(active_email, active_acc)
                if ok_ref:
                    ENGINE.save_accounts(hub_data)
                self.last_full_refresh_ts = now_ts
        else:
            active_acc = accounts[active_email]
            at, was_ref = self.switcher.ensure_fresh_token(active_acc)
            if was_ref:
                self.switcher.save_hub_accounts(hub_data)
            if at:
                quotas, resets, val_url = self.switcher.fetch_live_quota(at)
                if val_url:
                    active_acc["validation_blocked"] = True
                    active_acc["validation_url"] = val_url
                    self.switcher.save_hub_accounts(hub_data)
                elif quotas:
                    active_acc.setdefault("gemini", {})["quota_5h"] = quotas.get("gemini-5h", 1.0)
                    active_acc["gemini"]["quota_weekly"] = quotas.get("gemini-weekly", 1.0)
                    if "3p-5h" in quotas:
                        active_acc.setdefault("claude", {})["quota_5h"] = quotas["3p-5h"]
                    if "3p-weekly" in quotas:
                        active_acc.setdefault("claude", {})["quota_weekly"] = quotas["3p-weekly"]
                    if "gemini4-weekly" in quotas:
                        active_acc.setdefault("gemini4", {})["quota_weekly"] = quotas["gemini4-weekly"]
                    self.switcher.save_hub_accounts(hub_data)

        active_acc = accounts[active_email]
        g_info = active_acc.get("gemini") or {}
        c_info = active_acc.get("claude") or {}
        g_5h = _safe_float(g_info.get("quota_5h", 1.0), 1.0)
        g_wk = _safe_float(g_info.get("quota_weekly", 1.0), 1.0)
        c_5h = _safe_float(c_info.get("quota_5h", 1.0), 1.0)
        c_wk = _safe_float(c_info.get("quota_weekly", 1.0), 1.0)

        check_5h = c_5h if rot_mode == "claude" else g_5h
        check_wk = c_wk if rot_mode == "claude" else g_wk
        if check_wk <= EXHAUSTED_EPS:
            check_5h = 0.0

        # 2. 检查配额是否触发阈值或物理耗尽（threshold=0 时严格等到彻底耗尽 <= 0.0001 再切换）
        is_truly_exhausted = (check_5h <= EXHAUSTED_EPS or check_wk <= EXHAUSTED_EPS)
        if depletion_thresh <= EXHAUSTED_EPS:
            is_depleted = is_truly_exhausted
        else:
            is_depleted = (
                is_truly_exhausted
                or check_5h < depletion_thresh
                or check_wk < depletion_thresh
            )

        if not is_depleted and not active_acc.get("validation_blocked"):
            return False

        # 3. 检查人工干预保护锁：若配额尚未彻底枯竭且人工锁针对当前账号仍有效，暂缓切号；彻底耗尽 (<=0.0001) 时强制接管轮换
        lock = self.get_manual_lock()
        locked_email = (lock.get("locked_email") or lock.get("manual_account") or "") if lock else ""
        lock_applies = bool(lock) and (not locked_email or locked_email.lower() == active_email.lower())
        if lock_applies and not active_acc.get("validation_blocked") and not is_truly_exhausted:
            remaining_sec = int(lock.get("locked_until", 0) - time.time())
            logger.info(f"🔒 [人工保护锁生效中] 锁定账号: {locked_email or active_email}，剩余时长: {remaining_sec}s，暂缓切号")
            return False

        logger.warning(
            f"🚨 [配额耗尽预警] 账号: {active_email} ({rot_mode}/{rot_strategy}) · "
            f"5h={round(check_5h * 100, 1)}%, 周={round(check_wk * 100, 1)}%, 阈值={round(depletion_thresh * 100)}%，启动瀑布轮换！"
        )

        # 4. 寻找最佳备用候选
        next_email = self.pick_best_standby_account(
            accounts,
            active_email,
            rot_mode=rot_mode,
            depletion_thresh=depletion_thresh,
            strategy=rot_strategy,
            accounts_order=hub_data.get("accounts_order") or list(accounts.keys()),
        )
        if not next_email:
            logger.error("❌ 全池备用账号均已耗尽或处于不可用状态，无法自动切号！")
            return False

        logger.info(f"🚀 [自动瀑布切号] 触发账号平滑轮换 ({rot_strategy}): {active_email} -> {next_email}")
        ok, msg = self.switcher.switch_account(next_email, force_hot_switch=True, inject_recovery=True)
        if ok:
            # 成功切走后再给原账号施加 30 分钟防乒乓冷却锁
            self.exhausted_cooldown_map[active_email] = time.time() + 1800.0
            logger.info(f"✅ {msg}")
            return True
        else:
            # 目标切换失败，短冷却 5 分钟避免死循环撞墙
            self.exhausted_cooldown_map[next_email] = time.time() + 300.0
            logger.error(f"❌ 切换账号失败: {msg}")
            return False

    def run_daemon(self):
        """常驻守护进程循环"""
        logger.info(f"🛡️ Antigravity 配额看门狗守护进程已启动 (检查间隔: {self.check_interval}s)")
        while True:
            try:
                self.check_and_rotate_once()
            except Exception as e:
                logger.error(f"❌ 看门狗循环异常: {e}")
            time.sleep(self.check_interval)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [QuotaRotator] %(message)s"
    )
    rotator = AntigravityQuotaRotator()
    rotator.run_daemon()
