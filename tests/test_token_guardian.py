#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_token_guardian.py — 验证 Token 临期保鲜与系统全端凭据强一致性自愈机制
=============================================================================
覆盖六大核心契约：
1. ensure_fresh_token 临期偏置判定 (15分钟 / 900s 门禁)；
2. force=True 强制续签支持；
3. 活跃账号凭据全端原子同步 (secret-tool + oauth_creds.json + jetski-standalone-oauth-token)；
4. 401 Unauthorized 端点探测自动续签自愈；
5. auto_ingest 系统密钥环滞后自愈反向写回；
6. refresh_all_quotas 与 ensure_fresh_token 嵌入式自然保鲜 (Mac 原版纯粹架构，零额外线程)。
"""

import os
import sys
import time
import json
import unittest
from unittest.mock import patch, MagicMock

# 加入模块搜索路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.switcher import AntigravityPhysicalManager, format_rfc3339
from hub.server import HubEngine, TOKEN_REFRESH_SKEW_SECONDS, sanitize_load_code_assist_payload, render_table_rows


class TestTokenGuardian(unittest.TestCase):

    def setUp(self):
        self.engine = HubEngine()
        self.mgr = AntigravityPhysicalManager()

    def test_ensure_fresh_token_reuse_valid(self):
        """测试：Token 远未临期 (> 900s) 时 100% 复用，0 次网络请求"""
        now = int(time.time())
        acc = {
            "email": "test_reuse@example.com",
            "access_token": "valid_token_123",
            "refresh_token": "valid_rt_123",
            "expires_at": now + 2500,
            "expiry_timestamp": now + 2500
        }
        with patch.object(self.engine, "refresh_google_token") as mock_refresh:
            at, was_refreshed = self.engine.ensure_fresh_token(acc, force=False)
            self.assertEqual(at, "valid_token_123")
            self.assertFalse(was_refreshed)
            mock_refresh.assert_not_called()

    def test_ensure_fresh_token_skew_triggers_refresh(self):
        """测试：Token 处于临期窗口 (<= 900s) 时自动触发 Google OAuth 续签"""
        now = int(time.time())
        acc = {
            "email": "test_skew@example.com",
            "access_token": "stale_token_123",
            "refresh_token": "valid_rt_123",
            "expires_at": now + 600,  # 仅剩 10 分钟 (< 15分钟)
            "expiry_timestamp": now + 600
        }
        fake_new_token = {
            "access_token": "brand_new_token_456",
            "expires_in": 3600
        }
        with patch.object(self.engine, "refresh_google_token", return_value=fake_new_token):
            with patch.object(self.engine, "sync_active_credentials_to_system") as mock_sync:
                at, was_refreshed = self.engine.ensure_fresh_token(acc, force=False)
                self.assertEqual(at, "brand_new_token_456")
                self.assertTrue(was_refreshed)
                self.assertEqual(acc["access_token"], "brand_new_token_456")
                self.assertGreaterEqual(acc["expires_at"], now + 3590)

    def test_ensure_fresh_token_force_refresh(self):
        """测试：force=True 绕过剩余有效期检查直接触发续签 (用于 401 自愈)"""
        now = int(time.time())
        acc = {
            "email": "test_force@example.com",
            "access_token": "current_token_123",
            "refresh_token": "valid_rt_123",
            "expires_at": now + 3000,  # 剩余 50 分钟
            "expiry_timestamp": now + 3000
        }
        fake_new_token = {
            "access_token": "forced_new_token_789",
            "expires_in": 3600
        }
        with patch.object(self.engine, "refresh_google_token", return_value=fake_new_token):
            at, was_refreshed = self.engine.ensure_fresh_token(acc, force=True)
            self.assertEqual(at, "forced_new_token_789")
            self.assertTrue(was_refreshed)

    def test_active_account_syncs_to_system_on_refresh(self):
        """测试：活跃账号被刷新时，必须无感同步至系统底层钥匙串与 ~/.gemini/ 凭据池"""
        now = int(time.time())
        active_email = "active_user@example.com"
        acc = {
            "email": active_email,
            "access_token": "old_active_token",
            "refresh_token": "rt_active",
            "expires_at": now + 100,  # 临期
            "expiry_timestamp": now + 100
        }
        fake_new_token = {
            "access_token": "super_fresh_active_token",
            "expires_in": 3600
        }
        with patch.object(self.engine, "load_accounts", return_value={"active_email": active_email, "accounts": {active_email: acc}}):
            with patch.object(self.engine, "refresh_google_token", return_value=fake_new_token):
                with patch.object(self.engine, "sync_active_credentials_to_system") as mock_sync:
                    at, was_ref = self.engine.ensure_fresh_token(acc, force=False)
                    self.assertEqual(at, "super_fresh_active_token")
                    self.assertTrue(was_ref)
                    mock_sync.assert_called_once_with(
                        active_email,
                        "super_fresh_active_token",
                        "rt_active",
                        acc["expires_at"]
                    )

    def test_sync_all_active_credentials_writes_all_targets(self):
        """测试：sync_all_active_credentials 全目标原子写入契约"""
        email = "test_sync_targets@example.com"
        at = "test_at_12345"
        rt = "test_rt_12345"
        exp_ts = time.time() + 3600

        with patch.object(self.mgr, "write_to_linux_secret", return_value=True) as mock_sec:
            with patch.object(self.mgr, "sync_local_credentials") as mock_loc:
                ok = self.mgr.sync_all_active_credentials(email, at, rt, exp_ts)
                self.assertTrue(ok)
                mock_sec.assert_called_once()
                mock_loc.assert_called_once_with(email, at, rt, exp_ts)

    def test_quota_probe_401_self_healing(self):
        """测试：探测端点触发 401 Unauthorized 时，自动强制换取新 Token 并自愈重试"""
        email = "heal_user@example.com"
        acc = {
            "id": "acc_heal_1",
            "email": email,
            "access_token": "expired_token_401",
            "refresh_token": "rt_heal",
            "expires_at": time.time() + 2000,
            "gemini": {},
            "claude": {}
        }
        call_count = {"probe": 0}

        def mock_fetch(token):
            call_count["probe"] += 1
            if token == "expired_token_401":
                return {}, {}, None  # 模拟 401 失败返回空
            return {"gemini-5h": 0.85}, {"gemini-5h": "2026-11-10T23:00:00Z"}, None

        fake_refreshed = {
            "access_token": "healed_token_success",
            "expires_in": 3600
        }

        with patch.object(self.engine, "refresh_google_token", return_value=fake_refreshed):
            with patch.object(self.engine, "fetch_live_quota", side_effect=mock_fetch):
                with patch.object(self.engine, "sync_active_credentials_to_system"):
                    ok = self.engine.refresh_single_account_quota(email, acc)
                    self.assertTrue(ok)
                    self.assertEqual(call_count["probe"], 2)  # 1次401失败 + 1次自愈重试
                    self.assertEqual(acc["gemini"]["quota_5h"], 0.85)

    def test_refresh_clears_poisoned_gemini4_for_46(self):
        """测试：4.6 账号即使存在跨账号串台残留的 gemini4，刷新配额后必须强制归零清空"""
        email = "super46@example.com"
        acc = {
            "id": "acc_46",
            "email": email,
            "access_token": "valid_at_46",
            "refresh_token": "rt_46",
            "expires_at": time.time() + 2500,
            "gemini": {},
            "claude": {},
            "gemini4": {"quota_weekly": 0.2757, "reset_time_weekly": "2026-11-17T01:38:57Z"}
        }
        with patch.object(self.engine, "fetch_live_quota", return_value=({"gemini-5h": 0.4, "gemini-weekly": 0.5, "3p-5h": 1.0, "3p-weekly": 1.0}, {}, None)):
            with patch.object(self.engine, "fetch_available_models", return_value=("4.6", ["claude-sonnet-4-6", "claude-opus-4-6-thinking"])):
                with patch.object(self.engine, "_sync_antigravity_tools_cache"):
                    ok = self.engine.refresh_single_account_quota(email, acc)
                    self.assertTrue(ok)
                    self.assertEqual(acc["claude_version"], "4.6")
                    self.assertIsNone(acc["gemini4"])

    def test_auto_ingest_syncs_local_creds_on_newer_secret(self):
        """测试：IDE 自行续签 secret-tool 后，auto_ingest_system_account 同步更新 Hub 与本地 oauth_creds/jetski"""
        import datetime, subprocess
        email = "ide_renew@example.com"
        now = int(time.time())
        newer_exp = now + 3400
        newer_iso = datetime.datetime.fromtimestamp(newer_exp, tz=datetime.timezone.utc).isoformat()
        fake_kd = json.dumps({
            "token": {"access_token": "ide_fresh_at", "refresh_token": "rt_same", "expiry": newer_iso},
            "id_token_email": email
        })
        fake_hub = {
            "active_email": email,
            "accounts": {
                email: {
                    "id": "acc_ide_1",
                    "email": email,
                    "access_token": "old_hub_at",
                    "refresh_token": "rt_same",
                    "expires_at": now + 1000,
                    "gemini": {},
                    "claude": {}
                }
            }
        }
        mock_proc = MagicMock(returncode=0, stdout=fake_kd)
        with patch("subprocess.run", return_value=mock_proc):
            with patch.object(self.engine, "load_accounts", return_value=fake_hub):
                with patch.object(self.engine, "save_accounts") as mock_save:
                    with patch.object(self.engine, "sync_from_local_language_server", return_value=False):
                        with patch("core.switcher.AntigravityPhysicalManager.sync_local_credentials") as mock_local_sync:
                            em, is_new = self.engine.auto_ingest_system_account()
                            self.assertEqual(em, email)
                            self.assertFalse(is_new)
                            self.assertEqual(fake_hub["accounts"][email]["access_token"], "ide_fresh_at")
                            mock_local_sync.assert_called_once()
                            args = mock_local_sync.call_args[0]
                            self.assertEqual(args[0], email)
                            self.assertEqual(args[1], "ide_fresh_at")
                            mock_save.assert_called()

    def test_sync_from_local_language_server_captures_argon_and_ignores_carbon(self):
        """测试：sync_from_local_language_server 成功采集 gemini-4-argon 配额且忽略 gemini-4-carbon-disabled"""
        email = "duxilian88@example.com"
        fake_hub = {
            "active_email": email,
            "accounts": {
                email: {
                    "id": "acc_g4",
                    "email": email,
                    "access_token": "valid_token",
                    "gemini": {},
                    "claude": {},
                    "claude_version": "5.5"
                }
            }
        }
        mock_user_status = {
            "userStatus": {
                "email": email,
                "cascadeModelConfigData": {
                    "clientModelConfigs": [
                        {
                            "modelId": "gemini-4-argon-medium",
                            "label": "Gemini 4 Argon (Medium)",
                            "quotaInfo": {
                                "remainingFraction": 0.6018,
                                "resetTime": "2026-11-18T02:23:24Z"
                            }
                        },
                        {
                            "modelId": "gemini-4-carbon-disabled",
                            "label": "Gemini 4 Carbon",
                            "quotaInfo": {}
                        },
                        {
                            "modelId": "claude-opus-5-5-high",
                            "label": "Claude Opus 5.5 (High)",
                            "quotaInfo": {"remainingFraction": 0.48, "resetTime": "2026-11-16T12:47:25Z"}
                        }
                    ]
                }
            }
        }
        mock_quota_summary = {
            "response": {
                "groups": [
                    {
                        "displayName": "Gemini Models",
                        "buckets": [
                            {"bucketId": "gemini-weekly", "remainingFraction": 0.165, "resetTime": "2026-11-16T19:04:15Z"},
                            {"bucketId": "gemini-5h", "remainingFraction": 0.80, "resetTime": "2026-11-11T12:59:44Z"}
                        ]
                    },
                    {
                        "displayName": "Claude and GPT models",
                        "buckets": [
                            {"bucketId": "3p-weekly", "remainingFraction": 0.49, "resetTime": "2026-11-16T12:47:25Z"},
                            {"bucketId": "3p-5h", "remainingFraction": 1.0, "resetTime": "2026-11-11T16:33:40Z"}
                        ]
                    },
                    {
                        "displayName": "Gemini 4 Argon",
                        "buckets": [
                            {"bucketId": "gemini-argon-wtu-weekly", "remainingFraction": 0.6018, "resetTime": "2026-11-18T02:23:24Z"}
                        ]
                    }
                ]
            }
        }

        class FakeResp:
            def __init__(self, data):
                self.data = data
            def read(self):
                return self.data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("glob.glob", return_value=["/fake/daemon/daemon.json"]):
            with patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps({"pid": 99999, "httpPort": 40689, "csrfToken": "tok"}))):
                with patch("os.kill"):
                    with patch("urllib.request.urlopen") as mock_url:
                        # 第一次响应 GetUserStatus，第二次响应 RetrieveUserQuotaSummary
                        resp1 = FakeResp(json.dumps(mock_user_status).encode())
                        resp2 = FakeResp(json.dumps(mock_quota_summary).encode())
                        mock_url.side_effect = [resp1, resp2]

                        with patch.object(self.engine, "load_accounts", return_value=fake_hub):
                            with patch.object(self.engine, "save_accounts") as mock_save:
                                updated = self.engine.sync_from_local_language_server(fake_hub)
                                self.assertTrue(updated)
                                acc = fake_hub["accounts"][email]
                                self.assertIsNotNone(acc.get("gemini4"))
                                self.assertAlmostEqual(acc["gemini4"]["quota_weekly"], 0.6018, places=3)
                                self.assertEqual(acc["gemini4"]["reset_time_weekly"], "2026-11-18T02:23:24Z")
                                self.assertAlmostEqual(acc["gemini"]["quota_5h"], 0.80, places=2)
                                self.assertEqual(acc["gemini"]["reset_time_5h"], "2026-11-11T12:59:44Z")
                                self.assertEqual(acc["claude"]["reset_time_5h"], "2026-11-11T16:33:40Z")

    def test_macos_purity_alignment_and_no_app_storage_mutation(self):
        """验证 Linux Secret Service 凭据纯净度物理对齐 macOS Keychain，且绝不篡改 app_storage.json"""
        import tempfile
        from core.switcher import AntigravityPhysicalManager
        mgr = AntigravityPhysicalManager()

        captured_inputs = []

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                self.cmd = cmd
                self.returncode = 0
            def communicate(self, input=None, timeout=None):
                captured_inputs.append(input)
                return ("ok", "")

        with patch("subprocess.Popen", side_effect=FakePopen):
            ok = mgr.write_to_linux_secret("test_at", "test_rt", email="cakeai888@gmail.com", expiry_str="2026-11-18T12:00:00Z")
            self.assertTrue(ok)
            self.assertGreater(len(captured_inputs), 0)

            # 校验写入 Linux Secret Service 的 payload 结构 100% 对齐 macOS Keychain 纯净标准
            payload = json.loads(captured_inputs[0])
            self.assertEqual(payload["auth_method"], "consumer")
            self.assertIn("token", payload)
            self.assertEqual(payload["token"]["access_token"], "test_at")
            self.assertEqual(payload["token"]["refresh_token"], "test_rt")
            self.assertEqual(payload["token"]["token_type"], "Bearer")
            self.assertEqual(payload["token"]["expiry"], "2026-11-18T12:00:00Z")

            # 严格断言：绝不包含多余元数据字段，杜绝触发 React 前端误判
            self.assertNotIn("id_token_email", payload)
            self.assertNotIn("writer_id", payload)
            self.assertNotIn("expires_in", payload)
            self.assertNotIn("id_token", payload)

        # 验证 sync_local_credentials 绝不触碰 app_storage.json
        with patch("core.switcher.atomic_write_json", return_value=True) as mock_write:
            mgr.sync_local_credentials("cakeai888@gmail.com", "at", "rt", time.time() + 3600)
            written_paths = [call_args[0][0] for call_args in mock_write.call_args_list]
            # 必须断言没有任何写操作指向 app_storage.json
            for p in written_paths:
                self.assertNotIn("app_storage.json", p, f"违规写入了 app_storage: {p}")

    def test_ccpa_load_code_assist_sanitizer_preserves_unpaid_and_cleans_paid(self):
        """验证 CCPA 净化器：仅对拥有合法付费/standard-tier 的账号剥离 free-tier 地区阻断，纯无权限账号保持原样"""
        import gzip

        paid_payload = {
            "currentTier": {"id": "standard-tier", "name": "Antigravity"},
            "allowedTiers": [{"id": "standard-tier", "name": "Antigravity", "isDefault": True}],
            "ineligibleTiers": [
                {
                    "reasonCode": "UNSUPPORTED_LOCATION",
                    "reasonMessage": "Your current account is not eligible for Antigravity, because it is not currently available in your location.",
                    "tierId": "free-tier",
                    "tierName": "Antigravity"
                }
            ],
            "paidTier": {"id": "g1-ultra-tier", "name": "Google AI Ultra"}
        }

        # 1. 明文 JSON 测试 (cakeai888 Ultra 场景)
        raw_plain = json.dumps(paid_payload).encode("utf-8")
        cleaned_plain, modified_plain = sanitize_load_code_assist_payload(raw_plain, is_gzip=False)
        self.assertTrue(modified_plain)
        parsed_plain = json.loads(cleaned_plain.decode("utf-8"))
        self.assertEqual(parsed_plain["ineligibleTiers"], [])
        self.assertEqual(parsed_plain["paidTier"]["id"], "g1-ultra-tier")
        self.assertEqual(parsed_plain["allowedTiers"][0]["id"], "standard-tier")

        # 2. Gzip 压缩载荷测试 (保持 gzip 压缩格式)
        raw_gz = gzip.compress(raw_plain)
        cleaned_gz, modified_gz = sanitize_load_code_assist_payload(raw_gz, is_gzip=True)
        self.assertTrue(modified_gz)
        self.assertTrue(cleaned_gz.startswith(b"\x1f\x8b"))
        parsed_gz = json.loads(gzip.decompress(cleaned_gz).decode("utf-8"))
        self.assertEqual(parsed_gz["ineligibleTiers"], [])

        # 3. 纯无订阅且无 standard-tier 账号 (绝不篡改)
        unpaid_payload = {
            "allowedTiers": [],
            "ineligibleTiers": [
                {"reasonCode": "UNSUPPORTED_LOCATION", "tierId": "free-tier"}
            ]
        }
        raw_unpaid = json.dumps(unpaid_payload).encode("utf-8")
        cleaned_unpaid, modified_unpaid = sanitize_load_code_assist_payload(raw_unpaid, is_gzip=False)
        self.assertFalse(modified_unpaid)
        self.assertEqual(json.loads(cleaned_unpaid.decode("utf-8"))["ineligibleTiers"][0]["reasonCode"], "UNSUPPORTED_LOCATION")

    def test_ultra_account_gemini4_hydrogen_retained_with_claude_46(self):
        """验证 ULTRA / Gemini 4 (含 Hydrogen) 账号即使 Claude 为 4.6 也不被误清空 gemini4 配额，且在看板正确呈现"""
        import tempfile
        import hub.server as hub_server

        email = "cakeai888@gmail.com"
        acc = {
            "id": "acc_ultra_g4",
            "email": email,
            "tier": "PRO",
            "access_token": "ya29.fake_valid_ultra",
            "refresh_token": "rt_ultra",
            "expires_at": time.time() + 2500,
            "gemini": {},
            "claude": {},
            "gemini4": None
        }
        ent_mock = {"project": "aicode-consumers", "tier": "ULTRA", "has_gemini4": True}
        quotas_mock = (
            {"gemini-5h": 0.975, "gemini-weekly": 0.995, "3p-5h": 0.9999, "3p-weekly": 1.0},
            {"gemini-5h": "2026-11-18T07:51:47Z", "gemini-weekly": "2026-11-25T02:51:47Z"},
            None
        )
        with patch.object(self.engine, "probe_account_entitlement_and_g4", return_value=ent_mock):
            with patch.object(self.engine, "fetch_live_quota", return_value=quotas_mock):
                with patch.object(self.engine, "fetch_available_models", return_value=("4.6", ["claude-sonnet-4-6", "claude-opus-4-6-thinking"])):
                    with patch.object(self.engine, "_sync_antigravity_tools_cache"):
                        ok = self.engine.refresh_single_account_quota(email, acc)
                        self.assertTrue(ok)
                        self.assertEqual(acc["tier"], "ULTRA")
                        self.assertTrue(acc.get("gemini4_supported"))
                        self.assertIsNotNone(acc.get("gemini4"))
                        self.assertAlmostEqual(acc["gemini4"]["quota_weekly"], 0.995, places=3)

        # 验证 save_accounts 保留 ULTRA + gemini4_supported 的 gemini4 字段，且 render_table_rows 正确渲染而非 "—"
        with tempfile.TemporaryDirectory() as td:
            fake_data = {"active_email": email, "accounts": {email: acc}}
            with patch.object(hub_server, "ACCOUNTS_HUB_FILE", os.path.join(td, "accounts_hub.json")):
                with patch("hub.server.atomic_write_json", return_value=True):
                    with patch.object(self.engine, "sync_external_pools"):
                        self.engine.save_accounts(fake_data)
            self.assertIsNotNone(fake_data["accounts"][email]["gemini4"])
            self.assertAlmostEqual(fake_data["accounts"][email]["gemini4"]["quota_weekly"], 0.995, places=3)

            with patch.object(hub_server.ENGINE, "load_accounts", return_value=fake_data):
                html = render_table_rows(include_oob=False)
                self.assertIn('data-gemini4-w="0.995"', html)
                self.assertNotIn("未开通 Gemini 4", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
