#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_rotator_precision.py — v3.0.7 零阈值用尽切换与 1% 低周额度隔离回归测试
========================================================================
覆盖核心契约：
1. 保底告急阈值下限为 0%：设为 0.0 时，0.4% / 0.7% (1%) 绝不提前切走，仅在 <= 0.0001 时切换；
2. 人工保护锁仅在真正耗尽 (<= 0.0001) 或 validation_blocked 时破锁，不在 1%~2% 提前踢号，同时覆盖 check_wk 归零；
3. 1% 周额度账号 (0.005 <= quota_weekly < 0.015) 在 highest-quota / round-robin / least-used / sticky 四种策略
   与 TopG (switch_top_gemini_account) 下均被严格隔离，绝不因 5h=100% 或轮排相邻位抢占自动选择；
4. 0% (<0.005) 残余账号永不被 pick_best_standby_account 自动选中；
5. 全池无 >=2% 健康账号时，仅 1% 残丝池进入最终兜底；
6. 兼容 priority=null / token=null 等真实生产 JSON 字段，不触发 TypeError / AttributeError；
7. rot_mode='off' 冻结轮换；rot_mode='claude' 按 Claude 桶与 claude_threshold 判定。
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import hub.server as hub_server
from core.rotator import AntigravityQuotaRotator
from hub.server import HubEngine, get_hub_settings


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


class TestRotatorPrecision(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = self.tmpdir.name
        os.makedirs(os.path.join(self.data_dir, "data"), exist_ok=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_zero_threshold_keeps_residual_until_exhausted(self):
        """阈值 0% 时，0.4% 周 / 0.7% (1%) 周 / 1.5% 5h 均继续使用；仅 0.0 / <=0.0001 时切换"""
        _write_json(
            os.path.join(self.data_dir, "auto_rotation_config.json"),
            {"mode": "gemini", "enabled": True, "policy": "gemini_first"},
        )
        _write_json(
            os.path.join(self.data_dir, "data", "hub_settings.json"),
            {
                "rotation_strategy": "highest-quota",
                "gemini_threshold": 0.0,
                "claude_threshold": 0.0,
            },
        )
        accounts = {
            "active@test.com": {
                "email": "active@test.com",
                "refresh_token": "rt_active",
                "gemini": {"quota_5h": 0.65, "quota_weekly": 0.004},
                "claude": {"quota_5h": 1.0, "quota_weekly": 1.0},
                "priority": None,
                "token": None,
            },
            "standby@test.com": {
                "email": "standby@test.com",
                "refresh_token": "rt_standby",
                "gemini": {"quota_5h": 1.0, "quota_weekly": 0.50},
                "claude": {"quota_5h": 1.0, "quota_weekly": 0.50},
                "priority": None,
                "token": None,
            },
        }
        accounts_path = os.path.join(self.data_dir, "data", "accounts_hub.json")
        _write_json(accounts_path, {"active_email": "active@test.com", "accounts": accounts})

        rotator = AntigravityQuotaRotator(data_dir=self.data_dir)
        rotator.switcher.ensure_fresh_token = MagicMock(return_value=(None, False))
        rotator.switcher.switch_account = MagicMock(return_value=(True, "ok"))

        # Case 1: 0.4% 周额度仍未用尽 -> 绝不提前切走
        self.assertFalse(rotator.check_and_rotate_once())
        rotator.switcher.switch_account.assert_not_called()

        # Case 2: 0.4% 5h + 0.7% (1%) 周额度 -> 仍未耗尽，继续使用
        accounts["active@test.com"]["gemini"] = {"quota_5h": 0.004, "quota_weekly": 0.0073}
        _write_json(accounts_path, {"active_email": "active@test.com", "accounts": accounts})
        self.assertFalse(rotator.check_and_rotate_once())
        rotator.switcher.switch_account.assert_not_called()

        # Case 3: 5h 真正用尽 (=0.0001) + 有未过期人工锁 -> 破锁切走至 standby
        _write_json(
            os.path.join(self.data_dir, "manual_override_lock.json"),
            {"manual_account": "active@test.com", "locked_until": int(time.time()) + 600},
        )
        accounts["active@test.com"]["gemini"] = {"quota_5h": 0.0001, "quota_weekly": 0.30}
        _write_json(accounts_path, {"active_email": "active@test.com", "accounts": accounts})
        self.assertTrue(rotator.check_and_rotate_once())
        rotator.switcher.switch_account.assert_called_once_with(
            "standby@test.com", force_hot_switch=True, inject_recovery=True
        )

    def test_manual_lock_blocks_soft_threshold_but_yields_on_weekly_exhaustion(self):
        """人工锁对同一活跃账号有效：软阈值 (5% 下剩 2%) 暂缓切号；周额度真归零 (Claude 5h=1.0, w=0.0) 立即破锁"""
        _write_json(
            os.path.join(self.data_dir, "auto_rotation_config.json"),
            {"mode": "claude", "enabled": True, "policy": "claude_first"},
        )
        _write_json(
            os.path.join(self.data_dir, "data", "hub_settings.json"),
            {
                "rotation_strategy": "highest-quota",
                "gemini_threshold": 0.0,
                "claude_threshold": 0.05,
            },
        )
        _write_json(
            os.path.join(self.data_dir, "manual_override_lock.json"),
            {"manual_account": "c1@test.com", "locked_until": int(time.time()) + 600},
        )
        accounts = {
            "c1@test.com": {
                "email": "c1@test.com",
                "refresh_token": "rt1",
                "gemini": {"quota_5h": 1.0, "quota_weekly": 1.0},
                "claude": {"quota_5h": 0.025, "quota_weekly": 0.20},
            },
            "c2@test.com": {
                "email": "c2@test.com",
                "refresh_token": "rt2",
                "gemini": {"quota_5h": 1.0, "quota_weekly": 1.0},
                "claude": {"quota_5h": 1.0, "quota_weekly": 0.80},
            },
        }
        accounts_path = os.path.join(self.data_dir, "data", "accounts_hub.json")
        _write_json(accounts_path, {"active_email": "c1@test.com", "accounts": accounts})

        rotator = AntigravityQuotaRotator(data_dir=self.data_dir)
        rotator.switcher.ensure_fresh_token = MagicMock(return_value=(None, False))
        rotator.switcher.switch_account = MagicMock(return_value=(True, "ok"))

        # Claude 5h=2.5% < 5% 阈值，但尚未彻底耗尽且处于人工锁保护期内 -> 暂缓切号
        self.assertFalse(rotator.check_and_rotate_once())
        rotator.switcher.switch_account.assert_not_called()

        # Claude 原始 JSON 5h=1.0 但周额度=0.0 -> 周耗尽短路强制破锁切换
        accounts["c1@test.com"]["claude"] = {"quota_5h": 1.0, "quota_weekly": 0.0}
        _write_json(accounts_path, {"active_email": "c1@test.com", "accounts": accounts})
        self.assertTrue(rotator.check_and_rotate_once())
        rotator.switcher.switch_account.assert_called_once_with(
            "c2@test.com", force_hot_switch=True, inject_recovery=True
        )

    def test_one_percent_weekly_accounts_never_hijack_any_strategy_or_topg(self):
        """核心防呆：1% 周额度 (0.0073) 与 0% 周额度 (0.004) 账号在所有策略和 TopG 下均绝不抢占健康账号"""
        accounts = {
            "active@test.com": {
                "email": "active@test.com",
                "refresh_token": "rt0",
                "priority": None,
                "gemini": {"quota_5h": 0.0, "quota_weekly": 0.0},
            },
            # 位于 active 紧邻下一位、且 5h=100%、但周额度仅 0.73% (展示 1%) 的干扰账号
            "onepct_next@test.com": {
                "email": "onepct_next@test.com",
                "refresh_token": "rt1",
                "priority": None,
                "last_used_time": 100,
                "gemini": {"quota_5h": 1.0, "quota_weekly": 0.0073466},
            },
            # 另一枚周额度 0.4% (展示 0%) 但 5h=100% 的残丝干扰账号
            "zeropct@test.com": {
                "email": "zeropct@test.com",
                "refresh_token": "rt2",
                "priority": None,
                "last_used_time": 50,
                "gemini": {"quota_5h": 1.0, "quota_weekly": 0.004},
            },
            # 虽非 5h=100%，但周额度健康 (45%) 的真实可用账号
            "healthy_a@test.com": {
                "email": "healthy_a@test.com",
                "refresh_token": "rt3",
                "priority": None,
                "last_used_time": 500,
                "gemini": {"quota_5h": 0.87, "quota_weekly": 0.45},
            },
            # 最充沛健康账号
            "healthy_top@test.com": {
                "email": "healthy_top@test.com",
                "refresh_token": "rt4",
                "priority": None,
                "last_used_time": 900,
                "gemini": {"quota_5h": 0.98, "quota_weekly": 0.90},
            },
            # 无 Token 或被风控的健康配额假号也必须被跳过
            "blocked_fake@test.com": {
                "email": "blocked_fake@test.com",
                "refresh_token": "rt5",
                "validation_blocked": True,
                "gemini": {"quota_5h": 1.0, "quota_weekly": 1.0},
            },
            "notoken_fake@test.com": {
                "email": "notoken_fake@test.com",
                "refresh_token": "",
                "token": None,
                "gemini": {"quota_5h": 1.0, "quota_weekly": 1.0},
            },
        }
        order = [
            "healthy_top@test.com",
            "active@test.com",
            "onepct_next@test.com",
            "zeropct@test.com",
            "blocked_fake@test.com",
            "notoken_fake@test.com",
            "healthy_a@test.com",
        ]

        rotator = AntigravityQuotaRotator(depletion_threshold=0.0, data_dir=self.data_dir)

        # 1. highest-quota: healthy_top 胜出，1%/0% 残丝绝不靠 5h=100% 抢位
        self.assertEqual(
            rotator.pick_best_standby_account(accounts, "active@test.com", strategy="highest-quota", accounts_order=order),
            "healthy_top@test.com",
        )

        # 2. round-robin: 从 active 后顺延，自动跳过相邻的 onepct_next / zeropct / blocked / notoken，选中 healthy_a
        self.assertEqual(
            rotator.pick_best_standby_account(accounts, "active@test.com", strategy="round-robin", accounts_order=order),
            "healthy_a@test.com",
        )

        # 3. least-used: 尽管 onepct_next (100) / zeropct (50) 的 last_used 更早，仍只从 Tier 0 最早使用的 healthy_a (500) 中挑选
        self.assertEqual(
            rotator.pick_best_standby_account(accounts, "active@test.com", strategy="least-used", accounts_order=order),
            "healthy_a@test.com",
        )

        # 4. sticky: 不崩 priority=None，同样选 Tier 0 最优
        self.assertEqual(
            rotator.pick_best_standby_account(accounts, "active@test.com", strategy="sticky", accounts_order=order),
            "healthy_top@test.com",
        )

        # 5. 全池仅剩 1% 与 0% 残丝时：允许兜底选中 1% (onepct_next)，而 0% (zeropct < 0.005) 仍被屏蔽
        residual_only = {k: v for k, v in accounts.items() if k in ("active@test.com", "onepct_next@test.com", "zeropct@test.com")}
        self.assertEqual(
            rotator.pick_best_standby_account(residual_only, "active@test.com", strategy="highest-quota"),
            "onepct_next@test.com",
        )
        zero_only = {k: v for k, v in accounts.items() if k in ("active@test.com", "zeropct@test.com")}
        self.assertIsNone(
            rotator.pick_best_standby_account(zero_only, "active@test.com", strategy="highest-quota")
        )

        # 6. TopG (HubEngine.switch_top_gemini_account): 同样隔离 1% 周额度账号与风控/无 Token 账号
        accounts_path = os.path.join(self.data_dir, "data", "accounts_hub.json")
        _write_json(accounts_path, {"active_email": "active@test.com", "accounts": accounts})
        with patch.object(hub_server, "ACCOUNTS_HUB_FILE", accounts_path):
            eng = HubEngine()
            eng.switch_account = MagicMock(return_value=(True, "ok"))
            ok, msg, target = eng.switch_top_gemini_account()
        self.assertTrue(ok)
        self.assertEqual(target, "healthy_top@test.com")
        self.assertIn("98%", msg)
        self.assertIn("90%", msg)

    def test_off_mode_freezes_watchdog_and_hub_settings_defaults_zero(self):
        """off 模式彻底冻结自动轮换；get_hub_settings 缺失文件时默认双阈值均为 0.0"""
        _write_json(
            os.path.join(self.data_dir, "auto_rotation_config.json"),
            {"mode": "off", "enabled": False},
        )
        _write_json(
            os.path.join(self.data_dir, "data", "accounts_hub.json"),
            {
                "active_email": "dead@test.com",
                "accounts": {
                    "dead@test.com": {"gemini": {"quota_5h": 0.0, "quota_weekly": 0.0}},
                    "ok@test.com": {"gemini": {"quota_5h": 1.0, "quota_weekly": 1.0}},
                },
            },
        )
        rotator = AntigravityQuotaRotator(data_dir=self.data_dir)
        rotator.switcher.switch_account = MagicMock(return_value=(True, "ok"))
        self.assertFalse(rotator.check_and_rotate_once())
        rotator.switcher.switch_account.assert_not_called()

        missing_cfg_path = os.path.join(self.data_dir, "nonexistent_hub_settings.json")
        with patch.object(hub_server, "HUB_SETTINGS_PATH", missing_cfg_path):
            defaults = get_hub_settings()
        self.assertEqual(defaults["gemini_threshold"], 0.0)
        self.assertEqual(defaults["claude_threshold"], 0.0)
        self.assertEqual(defaults["rotation_strategy"], "highest-quota")


if __name__ == "__main__":
    unittest.main(verbosity=2)
