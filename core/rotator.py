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


class AntigravityQuotaRotator:
    """配额看门狗与自动轮转守护进程"""

    def __init__(
        self,
        check_interval: int = 10,
        depletion_threshold: float = 0.05,
        data_dir: str = BASE_DATA_DIR
    ):
        self.check_interval = check_interval
        self.depletion_threshold = depletion_threshold
        self.data_dir = data_dir
        self.switcher = AntigravityPhysicalManager(data_dir=self.data_dir)
        self.recovery = AntigravitySessionRecoveryManager()
        self.exhausted_cooldown_map: Dict[str, float] = {}
        self.last_full_refresh_ts: float = 0.0

    def get_manual_lock(self) -> Optional[Dict[str, Any]]:
        """检查是否存在有效的人工干预保护锁"""
        if not os.path.exists(MANUAL_OVERRIDE_LOCK_PATH):
            return None
        try:
            with open(MANUAL_OVERRIDE_LOCK_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("locked_until", 0) > time.time():
                return data
            return None
        except Exception:
            return None

    def pick_best_standby_account(self, accounts: Dict[str, Any], current_email: str) -> Optional[str]:
        """
        级联瀑布选号算法：
        1. 排除当前正在使用的账号及处于 30 分钟枯竭冷却期内的账号；
        2. 排除处于 validation_blocked 风控拦截态的账号；
        3. 排除 5 小时配额 (< 0.05) 或周度配额 (< 0.005) 已耗尽的账号；
        4. 综合打分：优先健康账号，按优先级 (priority) 与剩余配额综合排序。
        """
        now_ts = time.time()
        candidates = []
        for email, acc in accounts.items():
            if email == current_email:
                continue

            if self.exhausted_cooldown_map.get(email, 0) > now_ts:
                continue

            if acc.get("validation_blocked"):
                continue

            gemini_info = acc.get("gemini", {})
            g_5h = _safe_float(gemini_info.get("quota_5h", 1.0))
            g_weekly = _safe_float(gemini_info.get("quota_weekly", 1.0))

            if g_5h < self.depletion_threshold or g_weekly < 0.005:
                continue

            priority = acc.get("priority", 999)
            # 综合评分：高优先级值小，剩余配额高者得分高
            score = (1000 - priority) * 100 + (g_5h * 50) + (g_weekly * 10)
            candidates.append((score, email))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def check_and_rotate_once(self) -> bool:
        """执行单次配额检查与必要时的自动轮换 (支持毫秒级本地LS状态嗅探 + 级联瀑布无缝接力)"""
        try:
            from hub.server import ENGINE, get_auto_rotation_config
            hub_data = ENGINE.load_accounts()
        except Exception:
            hub_data = self.switcher.load_hub_accounts()
            ENGINE = None
            get_auto_rotation_config = None

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
            at, _ = self.switcher.ensure_fresh_token(active_acc)
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
        g_5h = _safe_float(active_acc.get("gemini", {}).get("quota_5h", 1.0), 1.0)
        g_wk = _safe_float(active_acc.get("gemini", {}).get("quota_weekly", 1.0), 1.0)
        c_5h = _safe_float(active_acc.get("claude", {}).get("quota_5h", 1.0), 1.0)
        c_wk = _safe_float(active_acc.get("claude", {}).get("quota_weekly", 1.0), 1.0)

        rot_mode = "gemini"
        if get_auto_rotation_config is not None:
            rot_cfg = get_auto_rotation_config()
            rot_mode = rot_cfg.get("mode", "gemini")

        check_5h = c_5h if rot_mode == "claude" else g_5h
        check_wk = c_wk if rot_mode == "claude" else g_wk

        # 2. 检查配额是否耗尽
        is_depleted = (check_5h < self.depletion_threshold or check_wk < 0.005)
        if not is_depleted and not active_acc.get("validation_blocked"):
            return False

        # 3. 检查人工干预保护锁：若配额尚未彻底枯竭且人工锁有效，暂缓切号；若配额彻底耗尽 (<0.02) 则强制接管轮换
        lock = self.get_manual_lock()
        if lock and not active_acc.get("validation_blocked") and check_5h >= 0.02:
            locked_email = lock.get("locked_email") or lock.get("manual_account")
            remaining_sec = int(lock.get("locked_until", 0) - time.time())
            logger.info(f"🔒 [人工保护锁生效中] 锁定账号: {locked_email}，剩余时长: {remaining_sec}s，暂缓切号")
            return False

        logger.warning(f"🚨 [配额耗尽预警] 账号: {active_email} ({rot_mode}) · 5h={round(check_5h * 100, 1)}%, 周={round(check_wk * 100, 1)}%，启动无缝瀑布轮换！")

        # 记录 30 分钟防乒乓冷却锁
        self.exhausted_cooldown_map[active_email] = time.time() + 1800.0

        # 4. 寻找最佳备用候选
        next_email = self.pick_best_standby_account(accounts, active_email)
        if not next_email:
            logger.error("❌ 全池备用账号均已耗尽或处于不可用状态，无法自动切号！")
            return False

        logger.info(f"🚀 [自动瀑布切号] 触发账号平滑轮换: {active_email} -> {next_email}")
        ok, msg = self.switcher.switch_account(next_email, force_hot_switch=True, inject_recovery=True)
        if ok:
            logger.info(f"✅ {msg}")
            return True
        else:
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
