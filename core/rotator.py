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
        check_interval: int = 60,
        depletion_threshold: float = 0.05,
        data_dir: str = BASE_DATA_DIR
    ):
        self.check_interval = check_interval
        self.depletion_threshold = depletion_threshold
        self.data_dir = data_dir
        self.switcher = AntigravityPhysicalManager(data_dir=self.data_dir)
        self.recovery = AntigravitySessionRecoveryManager()

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
        1. 排除当前正在使用的账号；
        2. 排除处于 validation_blocked 风控拦截态的账号；
        3. 排除 5 小时配额已耗尽 (< 0.05) 的账号；
        4. 综合打分：优先健康账号，按优先级 (priority) 与剩余配额综合排序。
        """
        candidates = []
        for email, acc in accounts.items():
            if email == current_email:
                continue

            if acc.get("validation_blocked"):
                continue

            gemini_info = acc.get("gemini", {})
            g_5h = _safe_float(gemini_info.get("quota_5h", 1.0))
            g_weekly = _safe_float(gemini_info.get("quota_weekly", 1.0))

            if g_5h < self.depletion_threshold:
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
        """执行单次配额检查与必要时的自动轮换"""
        hub_data = self.switcher.load_hub_accounts()
        accounts = hub_data.get("accounts", {})
        active_email = hub_data.get("active_email", "")

        if not active_email or active_email not in accounts:
            logger.info("ℹ️ 当前未指定活跃账号或账号池为空")
            return False

        # 1. 检查人工干预保护锁
        lock = self.get_manual_lock()
        if lock:
            locked_email = lock.get("locked_email")
            remaining_sec = int(lock.get("locked_until", 0) - time.time())
            logger.info(f"🔒 [人工保护锁生效中] 锁定账号: {locked_email}，剩余时长: {remaining_sec}s，守护进程暂停自动切号")
            return False

        # 2. 检查当前活跃账号配额
        active_acc = accounts[active_email]
        tok = active_acc.get("token", {})
        at = tok.get("access_token") or active_acc.get("access_token")

        if not at:
            logger.warning(f"⚠️ 当前活跃账号 {active_email} 缺少 Token")
            return False

        quotas, resets, val_url = self.switcher.fetch_live_quota(at)

        # 检查是否触发风控
        if val_url:
            logger.error(f"🚨 当前账号 {active_email} 触发 Google 403 风控验证！必须立即轮换！")
            active_acc["validation_blocked"] = True
            active_acc["validation_url"] = val_url
            self.switcher.save_hub_accounts(hub_data)
        else:
            # 更新配额数据
            g_5h = quotas.get("gemini_5h", active_acc.get("gemini", {}).get("quota_5h", 1.0))
            g_wk = quotas.get("gemini_weekly", active_acc.get("gemini", {}).get("quota_weekly", 1.0))
            active_acc.setdefault("gemini", {})["quota_5h"] = g_5h
            active_acc["gemini"]["quota_weekly"] = g_wk
            self.switcher.save_hub_accounts(hub_data)

            # 配额充沛无需轮换
            if g_5h >= self.depletion_threshold:
                logger.info(f"🟢 [配额健康] 账号: {active_email} · 5h 配额: {round(g_5h * 100, 1)}%")
                return False

            logger.warning(f"⚠️ [配额耗尽预警] 账号: {active_email} · 5h 配额剩余 {round(g_5h * 100, 1)}% < 阈值，准备轮换！")

        # 3. 寻找最佳备用候选
        next_email = self.pick_best_standby_account(accounts, active_email)
        if not next_email:
            logger.error("❌ 全池备用账号均已耗尽或处于不可用状态，无法自动切号！")
            return False

        logger.info(f"🚀 [自动瀑布切号] 触发账号平滑轮换: {active_email} -> {next_email}")
        ok, msg = self.switcher.switch_account(next_email, force_hot_switch=True)
        if ok:
            logger.info(f"✅ {msg}")
            # 4. 自动唤醒断点接力
            time.sleep(1.5)
            self.recovery.relay_all_active_sessions()
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
