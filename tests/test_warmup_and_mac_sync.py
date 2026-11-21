#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_warmup_and_mac_sync.py
防回归单元测试：覆盖 Git Mac 版全功能同步、真实 1-token 随机错峰预热与倒计时防遮蔽契约
"""

import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import hub.server as hub_server
from core.switcher import AntigravityPhysicalManager
from hub.importer import normalize_account_record
from hub.server import HubEngine, render_dashboard_html, render_quota_cell


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


class _FakeHTTPResp:
    def __init__(self, status: int, body: dict):
        self.status = status
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestWarmupAndMacSync(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = self.tmpdir.name
        os.makedirs(os.path.join(self.data_dir, "data"), exist_ok=True)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_sync_external_pools_handles_free_none_quota_5h(self):
        """sync_external_pools 处理 FREE 账号 quota_5h=None 时不得抛出 TypeError"""
        hub_data = {
            "active_email": "paid_demo@example.com",
            "accounts": {
                "paid_demo@example.com": {
                    "email": "paid_demo@example.com",
                    "has_5h": True,
                    "tier": "PAID_PRO",
                    "gemini": {"quota_5h": 0.88, "quota_weekly": 0.90},
                    "claude": {"quota_5h": 1.0, "quota_weekly": 0.95},
                },
                "free_demo@example.com": {
                    "email": "free_demo@example.com",
                    "has_5h": False,
                    "tier": "FREE",
                    "gemini": {"quota_5h": None, "quota_weekly": 0.72},
                    "claude": {"quota_5h": None, "quota_weekly": 1.0},
                },
            },
        }
        tools_dir = os.path.join(self.data_dir, "tools")
        tools_acc_dir = os.path.join(tools_dir, "accounts")
        hub_dir = os.path.join(self.data_dir, "data")

        with patch.object(hub_server, "ANTIGRAVITY_TOOLS_DIR", tools_dir), \
             patch.object(hub_server, "ANTIGRAVITY_TOOLS_ACCOUNTS_DIR", tools_acc_dir), \
             patch.object(hub_server, "HUB_DIR", hub_dir):
            eng = HubEngine()
            eng.sync_external_pools(hub_data)

        pool_file = os.path.join(self.data_dir, "antigravity_account_pool.json")
        self.assertTrue(os.path.isfile(pool_file))
        with open(pool_file, "r", encoding="utf-8") as f:
            pool = json.load(f)
        self.assertEqual(len(pool), 2)
        free_entry = next(x for x in pool if x["email"] == "free_demo@example.com")
        self.assertEqual(free_entry["last_5h_fraction"], 1.0)

    def test_phantom_3p_5h_without_gemini_5h_classified_as_free(self):
        """当官网仅返回 gemini-weekly + 无 resetTime 的 3p-5h 而无 gemini-5h 时，必须严谨判为 FREE"""
        email = "free_edge_demo@example.com"
        acc = {
            "id": "acc_edge_1",
            "email": email,
            "access_token": "at_edge",
            "refresh_token": "rt_edge",
            "expires_at": int(time.time()) + 3600,
            "gemini": {},
            "claude": {},
        }
        eng = HubEngine()
        quotas = {"gemini-weekly": 1.0, "3p-weekly": 1.0, "3p-5h": 1.0}
        resets = {"gemini-weekly": "2026-11-28T03:00:00Z"}
        with patch.object(eng, "fetch_live_quota", return_value=(quotas, resets, None)), \
             patch.object(eng, "fetch_available_models", return_value=("4.6", ["claude-sonnet-4-6"])), \
             patch.object(eng, "_sync_antigravity_tools_cache"):
            ok = eng.refresh_single_account_quota(email, acc)

        self.assertTrue(ok)
        self.assertFalse(acc["has_5h"])
        self.assertIsNone(acc["gemini"]["quota_5h"])
        self.assertIsNone(acc["claude"]["quota_5h"])
        self.assertEqual(acc["gemini"]["reset_time_5h"], "")
        self.assertEqual(acc["claude"]["reset_time_5h"], "")

    def test_warmup_ping_payload_and_failure_never_forges_countdown(self):
        """send_real_warmup_ping 必须携带 project 字段与准确模型；HTTP 500 失败绝不伪造倒计时"""
        mgr = AntigravityPhysicalManager(data_dir=self.data_dir)
        captured_bodies = []

        def fake_urlopen(req, timeout=12, context=None):
            captured_bodies.append(json.loads(req.data.decode("utf-8")))
            return _FakeHTTPResp(200, {"response": {"usageMetadata": {"totalTokenCount": 5}}})

        email_paid = "paid_demo@example.com"
        email_free_pro = "freepro_demo@example.com"
        accounts_path = os.path.join(self.data_dir, "data", "accounts_hub.json")
        _write_json(
            accounts_path,
            {
                "active_email": email_paid,
                "accounts": {
                    email_paid: {
                        "email": email_paid,
                        "tier": "PAID_PRO",
                        "has_5h": True,
                        "claude_version": "5.5",
                        "claude_models": ["claude-sonnet-5-5-low"],
                        "access_token": "at_paid",
                        "refresh_token": "rt_paid",
                        "expiry_timestamp": int(time.time()) + 3600,
                        "gemini": {"quota_5h": 1.0, "quota_weekly": 0.8},
                        "claude": {"quota_5h": 1.0, "quota_weekly": 0.8},
                    },
                    email_free_pro: {
                        "email": email_free_pro,
                        "tier": "FREE_PRO",
                        "has_5h": True,
                        "claude_version": "4.6",
                        "claude_models": ["claude-sonnet-4-6"],
                        "access_token": "at_fp",
                        "refresh_token": "rt_fp",
                        "expiry_timestamp": int(time.time()) + 3600,
                        "gemini": {"quota_5h": 1.0, "quota_weekly": 0.9},
                        "claude": {"quota_5h": 1.0, "quota_weekly": 0.9},
                    },
                },
            },
        )

        future_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(time.time()) + 17998))
        live_ret = ({"gemini-5h": 1.0, "gemini-weekly": 0.8, "3p-5h": 0.9999, "3p-weekly": 0.8},
                    {"gemini-5h": future_iso, "3p-5h": future_iso}, None)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep"), \
             patch.object(mgr, "fetch_live_quota", return_value=live_ret):
            hd = mgr.load_hub_accounts()
            res_paid = mgr.warmup_single_account(dict(hd["accounts"][email_paid], email=email_paid), warmup_mode="dual")
            res_fp = mgr.warmup_single_account(dict(hd["accounts"][email_free_pro], email=email_free_pro), warmup_mode="dual")

        self.assertEqual(res_paid["status"], "success")
        self.assertEqual(res_fp["status"], "success")
        self.assertTrue(all(b.get("project") == "aicode-consumers" for b in captured_bodies))
        sent_models = [b.get("model") for b in captured_bodies]
        self.assertIn("gemini-3.8-flash-low", sent_models)
        self.assertIn("claude-sonnet-5-5-low", sent_models)
        self.assertIn("claude-sonnet-4-6", sent_models)

        # HTTP 500 失败场景：严禁伪造 reset_time_5h 或返回 success
        fail_email = "fail_demo@example.com"
        _write_json(
            accounts_path,
            {
                "active_email": fail_email,
                "accounts": {
                    fail_email: {
                        "email": fail_email,
                        "tier": "FREE_PRO",
                        "has_5h": True,
                        "claude_version": "4.6",
                        "access_token": "at_fail",
                        "refresh_token": "rt_fail",
                        "expiry_timestamp": int(time.time()) + 3600,
                        "gemini": {"quota_5h": 1.0, "quota_weekly": 0.9, "reset_time_5h": ""},
                        "claude": {"quota_5h": 1.0, "quota_weekly": 0.9, "reset_time_5h": ""},
                    }
                },
            },
        )
        http_500 = urllib.error.HTTPError("https://example.com", 500, "err", {}, BytesIO(b"upstream err"))
        with patch("urllib.request.urlopen", side_effect=http_500):
            res_fail = mgr.warmup_single_account(dict(mgr.load_hub_accounts()["accounts"][fail_email], email=fail_email))

        self.assertEqual(res_fail["status"], "failed")
        hd_after = mgr.load_hub_accounts()
        self.assertEqual(hd_after["accounts"][fail_email]["gemini"]["reset_time_5h"], "")
        self.assertEqual(hd_after["accounts"][fail_email]["claude"]["reset_time_5h"], "")

    def test_staggered_warmup_skips_free_and_active_accounts(self):
        """错峰调度跳过 FREE 与已在走倒计时的 PRO 账号，到期仅触发待预热 PRO 账号"""
        mgr = AntigravityPhysicalManager(data_dir=self.data_dir)
        now_ts = int(time.time())
        active_reset_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts + 12000))
        accounts_path = os.path.join(self.data_dir, "data", "accounts_hub.json")

        accounts = {
            "active_cd@example.com": {
                "email": "active_cd@example.com",
                "tier": "PAID_PRO",
                "has_5h": True,
                "refresh_token": "rt1",
                "gemini": {"quota_5h": 0.70, "quota_weekly": 0.80, "reset_time_5h": active_reset_iso},
                "claude": {"quota_5h": 0.90, "quota_weekly": 0.80, "reset_time_5h": active_reset_iso},
            },
            "idle_pro@example.com": {
                "email": "idle_pro@example.com",
                "tier": "FREE_PRO",
                "has_5h": True,
                "refresh_token": "rt2",
                "gemini": {"quota_5h": 1.0, "quota_weekly": 0.95, "reset_time_5h": ""},
                "claude": {"quota_5h": 1.0, "quota_weekly": 1.0, "reset_time_5h": ""},
            },
            "free_user@example.com": {
                "email": "free_user@example.com",
                "tier": "FREE",
                "has_5h": False,
                "refresh_token": "rt3",
                "gemini": {"quota_5h": None, "quota_weekly": 1.0, "reset_time_5h": ""},
                "claude": {"quota_5h": None, "quota_weekly": 1.0, "reset_time_5h": ""},
            },
        }
        _write_json(accounts_path, {"active_email": "active_cd@example.com", "accounts": accounts})

        acc_list = [dict(v, email=k) for k, v in accounts.items()]
        mgr.rebalance_and_align_staggered_ladder(acc_list, force=False, stagger_sec=60, warmup_mode="dual")

        sched = mgr.load_warmup_schedule()
        self.assertNotIn("free_user@example.com", sched)
        self.assertIn("idle_pro@example.com", sched)
        # 绝不伪造 accounts_hub.json 的 reset_time_5h
        hd_disk = mgr.load_hub_accounts()
        self.assertEqual(hd_disk["accounts"]["idle_pro@example.com"]["gemini"]["reset_time_5h"], "")

        # 到期后自动触发仅点名 idle_pro
        sched["idle_pro@example.com"]["next_warmup_ts"] = now_ts - 5
        mgr.save_warmup_schedule(sched)
        with patch.object(mgr, "warmup_single_account", return_value={"email": "idle_pro@example.com", "status": "success"}) as mock_wu:
            triggered = mgr.check_and_trigger_due_staggered_warmup(stagger_sec=60, warmup_mode="dual")

        self.assertEqual(triggered, 1)
        mock_wu.assert_called_once()
        self.assertEqual(mock_wu.call_args[0][0]["email"], "idle_pro@example.com")

    def test_render_quota_cell_displays_countdown_at_100pct(self):
        """即使 5h 额度为 100% (1.0)，只要存在有效倒计时，必须展示真实倒计时而非满额"""
        html_active = render_quota_cell(1.0, 0.90, "4h 58m", "6d 10h", model_type="gemini", has_5h=True)
        self.assertIn("4h 58m", html_active)
        self.assertNotIn("满额", html_active)

        html_unwarmed = render_quota_cell(1.0, 0.90, "", "6d 10h", model_type="gemini", has_5h=True)
        self.assertIn("待预热", html_unwarmed)
        self.assertNotIn("满额", html_unwarmed)

    def test_mac_web_dashboard_parity_and_zero_lan_leak(self):
        """验证 Git Mac Web 看板具备活跃类别徽标与三档快筛，且无任何内网 IP 硬编码泄漏"""
        sample_accounts = {
            "active_email": "alpha@example.com",
            "accounts": {
                "alpha@example.com": {
                    "email": "alpha@example.com",
                    "tier": "PAID_PRO",
                    "has_5h": True,
                    "claude_version": "5.5",
                    "claude_models": ["claude-sonnet-5-5-low"],
                    "gemini": {"quota_5h": 0.99, "quota_weekly": 0.70, "reset_time_5h": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 14000))},
                    "claude": {"quota_5h": 1.0, "quota_weekly": 0.90, "reset_time_5h": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 15000))},
                    "refresh_token": "rt_a",
                },
                "beta@example.com": {
                    "email": "beta@example.com",
                    "tier": "FREE",
                    "has_5h": False,
                    "claude_version": "4.6",
                    "gemini": {"quota_5h": None, "quota_weekly": 0.85, "reset_time_5h": ""},
                    "claude": {"quota_5h": None, "quota_weekly": 1.0, "reset_time_5h": ""},
                    "refresh_token": "rt_b",
                },
            },
        }
        with patch.object(hub_server.ENGINE, "load_accounts", return_value=sample_accounts):
            html = render_dashboard_html()

        self.assertIn("active-tier-paid", html)
        self.assertIn('data-tier-filter="PAID_PRO"', html)
        self.assertIn('data-tier-filter="FREE_PRO"', html)
        self.assertIn('data-tier-filter="FREE"', html)
        self.assertNotIn("10.0.0." + "200", html)
        self.assertNotIn("01 M4", html)

    def test_importer_handles_free_none_quota_5h(self):
        """importer.normalize_account_record 安全接纳 FREE 账号 quota_5h=None 并保留三档元数据"""
        rec = normalize_account_record({
            "email": "free_imp@example.com",
            "tier": "FREE",
            "has_5h": False,
            "refresh_token": "rt_free",
            "gemini": {"quota_5h": None, "quota_weekly": 0.65},
            "claude": {"quota_5h": None, "quota_weekly": 1.0},
        })
        self.assertIsNotNone(rec)
        self.assertEqual(rec["tier"], "FREE")
        self.assertFalse(rec["has_5h"])
        self.assertFalse(rec["pro"])
        self.assertIsNone(rec["gemini"]["quota_5h"])
        self.assertIsNone(rec["claude"]["quota_5h"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
