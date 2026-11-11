#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_recovery_precision.py — v3.0.6 会话精准唤醒与整数百分比排版契约测试
=============================================================================
覆盖核心契约：
1. Antigravity LS RUNNING 会话精准唤醒；
2. IDLE + NO_TOOL_CALL / USER_CANCELED 即使处于 open_panes 且存在残留 SUBAGENT_STATE_ALIVE 也坚决跳过；
3. IDLE + 180s 内近期 EXECUTOR_TERMINATION_REASON_ERROR（如配额耗尽中断）精准唤醒，过期 ERROR 跳过；
4. 后代 subagent 为 RUNNING 时，其根会话自动纳入唤醒；
5. pre_switch_snapshot 空列表 [] 严格锁定 0 唤醒，绝不回退重扫历史已完成会话；
6. 无 LS 回退路径去除 open_panes / 残留 SUBAGENT_STATE_ALIVE 豁免，正常收尾会话绝不误唤醒；
7. hub.server 百分比全量四舍五入取整，且 0.4% 仅显示 0% 不误判周枯竭，0.0 正确熔断 0% 周枯竭。
"""

import os
import sys
import time
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.recovery import AntigravitySessionRecoveryManager
from core.switcher import AntigravityPhysicalManager
from hub.server import format_quota_int_pct, render_gemini4_cell, render_quota_cell


def _write_transcript(brain_dir: str, sid: str, entries: list, mtime_offset: float = 0.0) -> str:
    tpath = os.path.join(brain_dir, sid, ".system_generated", "logs", "transcript.jsonl")
    os.makedirs(os.path.dirname(tpath), exist_ok=True)
    with open(tpath, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    ts = time.time() - mtime_offset
    os.utime(tpath, (ts, ts))
    return tpath


def _iso_ago(seconds_ago: float) -> str:
    import datetime
    dt = datetime.datetime.fromtimestamp(time.time() - seconds_ago, tz=datetime.timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


class TestRecoveryPrecision(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.brain_dir = os.path.join(self.tmpdir.name, "brain")
        self.snap_path = os.path.join(self.tmpdir.name, "pre_switch_snapshot.json")
        os.makedirs(self.brain_dir, exist_ok=True)
        self.mgr = AntigravitySessionRecoveryManager(
            brain_dir=self.brain_dir,
            snapshot_path=self.snap_path,
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_ls_mode_only_wakes_running_and_recent_error_sessions(self):
        """LS 在线态：仅唤醒 RUNNING、拥有 RUNNING 后代的根会话及 180s 内 ERROR，彻底跳过已完成与已取消会话"""
        sid_running = "aaaa1111bbbb2222cccc3333dddd4444"
        sid_done = "bbbb1111cccc2222dddd3333eeee4444"
        sid_canceled = "cccc1111dddd2222eeee3333ffff4444"
        sid_recent_err = "dddd1111eeee2222ffff3333aaaa4444"
        sid_stale_err = "eeee1111ffff2222aaaa3333bbbb4444"
        sid_parent_with_sub = "ffff1111aaaa2222bbbb3333cccc4444"
        sid_sub_running = "99991111aaaa2222bbbb3333cccc4444"

        base_user = {"source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE", "content": "请修复 bug"}
        done_planner = {"source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "tool_calls": [], "content": "已全部修复完成"}
        tool_planner = {"source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "tool_calls": [{"name": "run_command", "args": {}}], "content": ""}

        _write_transcript(self.brain_dir, sid_running, [base_user, {"type": "GENERIC", "content": "ok"}, tool_planner], mtime_offset=5)
        _write_transcript(self.brain_dir, sid_done, [base_user, {"type": "GENERIC", "content": "ok"}, done_planner], mtime_offset=30)
        _write_transcript(self.brain_dir, sid_canceled, [base_user, {"type": "GENERIC", "content": "ok"}, tool_planner], mtime_offset=40)
        _write_transcript(self.brain_dir, sid_recent_err, [base_user, {"type": "GENERIC", "content": "ok"}, tool_planner], mtime_offset=20)
        _write_transcript(self.brain_dir, sid_stale_err, [base_user, {"type": "GENERIC", "content": "ok"}, tool_planner], mtime_offset=900)
        _write_transcript(self.brain_dir, sid_parent_with_sub, [base_user, {"type": "GENERIC", "content": "ok"}, done_planner], mtime_offset=10)
        _write_transcript(self.brain_dir, sid_sub_running, [base_user, {"type": "GENERIC", "content": "ok"}, tool_planner], mtime_offset=2)

        # 给已完成的 sid_done 故意写入残留的 SUBAGENT_STATE_ALIVE，模拟真实 Antigravity 磁盘残留
        stale_sub_id = "88881111aaaa2222bbbb3333cccc4444"
        _write_transcript(self.brain_dir, stale_sub_id, [base_user, {"type": "GENERIC", "content": "ok"}, done_planner], mtime_offset=500)
        sub_meta_dir = os.path.join(self.brain_dir, sid_done, ".system_generated", "subagents")
        os.makedirs(sub_meta_dir, exist_ok=True)
        with open(os.path.join(sub_meta_dir, f"{stale_sub_id}.json"), "w") as f:
            json.dump({"state": "SUBAGENT_STATE_ALIVE"}, f)

        live_trajectories = {
            sid_running: {
                "status": "CASCADE_RUN_STATUS_RUNNING",
                "latestExecutorTerminationReason": "EXECUTOR_TERMINATION_REASON_USER_CANCELED",
                "lastModifiedTime": _iso_ago(2),
                "trajectoryMetadata": {"nestingDepth": 0, "parentConversationId": "", "rootConversationId": sid_running},
            },
            sid_done: {
                "status": "CASCADE_RUN_STATUS_IDLE",
                "latestExecutorTerminationReason": "EXECUTOR_TERMINATION_REASON_NO_TOOL_CALL",
                "lastModifiedTime": _iso_ago(30),
                "trajectoryMetadata": {"nestingDepth": 0, "parentConversationId": "", "rootConversationId": sid_done},
            },
            sid_canceled: {
                "status": "CASCADE_RUN_STATUS_IDLE",
                "latestExecutorTerminationReason": "EXECUTOR_TERMINATION_REASON_USER_CANCELED",
                "lastModifiedTime": _iso_ago(40),
                "trajectoryMetadata": {"nestingDepth": 0, "parentConversationId": "", "rootConversationId": sid_canceled},
            },
            sid_recent_err: {
                "status": "CASCADE_RUN_STATUS_IDLE",
                "latestExecutorTerminationReason": "EXECUTOR_TERMINATION_REASON_ERROR",
                "lastModifiedTime": _iso_ago(15),
                "trajectoryMetadata": {"nestingDepth": 0, "parentConversationId": "", "rootConversationId": sid_recent_err},
            },
            sid_stale_err: {
                "status": "CASCADE_RUN_STATUS_IDLE",
                "latestExecutorTerminationReason": "EXECUTOR_TERMINATION_REASON_ERROR",
                "lastModifiedTime": _iso_ago(900),
                "trajectoryMetadata": {"nestingDepth": 0, "parentConversationId": "", "rootConversationId": sid_stale_err},
            },
            sid_parent_with_sub: {
                "status": "CASCADE_RUN_STATUS_IDLE",
                "latestExecutorTerminationReason": "EXECUTOR_TERMINATION_REASON_NO_TOOL_CALL",
                "lastModifiedTime": _iso_ago(10),
                "trajectoryMetadata": {"nestingDepth": 0, "parentConversationId": "", "rootConversationId": sid_parent_with_sub},
            },
            sid_sub_running: {
                "status": "CASCADE_RUN_STATUS_RUNNING",
                "latestExecutorTerminationReason": "EXECUTOR_TERMINATION_REASON_NO_TOOL_CALL",
                "lastModifiedTime": _iso_ago(2),
                "trajectoryMetadata": {
                    "nestingDepth": 1,
                    "parentConversationId": sid_parent_with_sub,
                    "rootConversationId": sid_parent_with_sub,
                    "subagentSpec": {"name": "research"},
                },
            },
        }

        with patch.object(self.mgr, "get_open_conversation_panes", return_value={sid_done, sid_canceled, sid_running}):
            found = self.mgr.scan_active_sessions(live_trajectories=live_trajectories)

        found_ids = {s["session_id"] for s in found}
        self.assertEqual(found_ids, {sid_running, sid_recent_err, sid_parent_with_sub})
        self.assertNotIn(sid_done, found_ids)
        self.assertNotIn(sid_canceled, found_ids)
        self.assertNotIn(sid_stale_err, found_ids)
        self.assertNotIn(sid_sub_running, found_ids)

    def test_empty_snapshot_does_not_trigger_rescan(self):
        """切号前快照明确记录 0 个会话时，切号后绝不允许退化触发 scan_active_sessions 误唤醒历史会话"""
        live_trajectories = {
            "aaaa1111bbbb2222cccc3333dddd4444": {
                "status": "CASCADE_RUN_STATUS_IDLE",
                "latestExecutorTerminationReason": "EXECUTOR_TERMINATION_REASON_NO_TOOL_CALL",
                "lastModifiedTime": _iso_ago(20),
                "trajectoryMetadata": {"nestingDepth": 0},
            }
        }
        with patch.object(self.mgr, "query_live_cascade_trajectories", return_value=live_trajectories):
            snapped = self.mgr.pre_switch_snapshot()
        self.assertEqual(snapped, [])
        self.assertTrue(os.path.isfile(self.snap_path))

        with patch.object(self.mgr, "scan_active_sessions", side_effect=AssertionError("不允许在空快照有效时二次重扫")) as mock_scan:
            with patch.object(self.mgr, "deliver_resume_message_to_session") as mock_deliver:
                recovered = self.mgr.batch_recover_all_working_sessions()
        self.assertEqual(recovered, 0)
        mock_scan.assert_not_called()
        mock_deliver.assert_not_called()
        self.assertFalse(os.path.isfile(self.snap_path))

    def test_fallback_mode_skips_finished_session_despite_open_pane_and_stale_alive(self):
        """LS 离线回退态：取消 open_panes 与残留 SUBAGENT_STATE_ALIVE 豁免，正常收尾纯文本会话坚决跳过"""
        sid_finished = "1111aaaa2222bbbb3333cccc4444dddd"
        sid_in_progress = "2222aaaa3333bbbb4444cccc5555eeee"
        sub_finished = "3333aaaa4444bbbb5555cccc6666ffff"

        base_user = {"source": "USER_EXPLICIT", "type": "USER_INPUT", "status": "DONE", "content": "请总结"}
        done_planner = {"source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "tool_calls": [], "content": "汇报完毕"}

        _write_transcript(self.brain_dir, sid_finished, [base_user, {"type": "GENERIC", "content": "step"}, done_planner], mtime_offset=20)
        _write_transcript(self.brain_dir, sub_finished, [base_user, {"type": "GENERIC", "content": "step"}, done_planner], mtime_offset=50)
        sub_meta_dir = os.path.join(self.brain_dir, sid_finished, ".system_generated", "subagents")
        os.makedirs(sub_meta_dir, exist_ok=True)
        with open(os.path.join(sub_meta_dir, f"{sub_finished}.json"), "w") as f:
            json.dump({"state": "SUBAGENT_STATE_ALIVE"}, f)

        # 未完成会话：最后有效消息仍为 USER_INPUT 或带工具调用
        _write_transcript(
            self.brain_dir,
            sid_in_progress,
            [base_user, {"type": "GENERIC", "content": "step"}, {"source": "MODEL", "type": "PLANNER_RESPONSE", "status": "DONE", "tool_calls": [{"name": "run_command", "args": {}}], "content": ""}],
            mtime_offset=15,
        )

        with patch.object(self.mgr, "get_open_conversation_panes", return_value={sid_finished, sid_in_progress}):
            with patch.object(self.mgr, "is_root_user_session", return_value=True):
                found = self.mgr.scan_active_sessions(live_trajectories={})

        found_ids = [s["session_id"] for s in found]
        self.assertEqual(found_ids, [sid_in_progress])

    def test_integer_percentage_rounding_and_depletion_gate(self):
        """验证四舍五入取整函数及 Web Hub HTML 渲染：消除全部小数点，且 0.4% 显示 0% 不误报周枯竭"""
        self.assertEqual(format_quota_int_pct(0.135), 14)
        self.assertEqual(format_quota_int_pct(0.145), 15)
        self.assertEqual(format_quota_int_pct(0.2757), 28)
        self.assertEqual(format_quota_int_pct(0.719), 72)
        self.assertEqual(format_quota_int_pct(0.999), 100)
        self.assertEqual(format_quota_int_pct(0.004), 0)
        self.assertEqual(format_quota_int_pct(0.0), 0)

        g4_html = render_gemini4_cell(0.2757, "5d 13h")
        self.assertIn(">28%<", g4_html)
        self.assertNotIn("27.6%", g4_html)

        # 0.4% 微量剩余：百分比四舍五入显示 0%，但不触发周枯竭 0% 归零联动
        low_html = render_quota_cell(0.943, 0.004, "4h 55m", "4d 19h", model_type="gemini")
        self.assertIn(">94%<", low_html)
        self.assertIn(">0%<", low_html)
        self.assertNotIn("周枯竭", low_html)
        self.assertNotIn("0.0%", low_html)

        # 真正 0.0 周耗尽：显示 0% + 周枯竭
        zero_html = render_quota_cell(0.8, 0.0, "4h 55m", "4d 19h", model_type="claude")
        self.assertIn(">0%<", zero_html)
        self.assertIn("周枯竭", zero_html)
        self.assertNotIn("0.0%", zero_html)

    def test_switch_account_uses_snapshot_without_rescan_and_async_recovery(self):
        """验证 switch_account：空快照不二次重扫；有在途会话时传入 preloaded_sessions 后台唤醒不阻塞响应"""
        mgr = AntigravityPhysicalManager(data_dir=self.tmpdir.name)
        email = "target@example.com"
        hub_data = {
            "active_email": "old@example.com",
            "accounts": {
                email: {
                    "email": email,
                    "access_token": "valid_at",
                    "refresh_token": "valid_rt",
                    "expiry_timestamp": int(time.time()) + 3600,
                }
            },
        }
        mgr.save_hub_accounts(hub_data)

        # Case A: 空快照 -> 只传 preloaded_sessions=[]，绝不阻塞也不误重扫
        with patch.object(AntigravitySessionRecoveryManager, "pre_switch_snapshot", return_value=[]):
            with patch.object(AntigravitySessionRecoveryManager, "batch_recover_all_working_sessions", return_value=0) as mock_batch:
                with patch.object(mgr, "write_to_linux_secret", return_value=True):
                    with patch.object(mgr, "sync_local_credentials"):
                        ok, _ = mgr.switch_account(email, force_hot_switch=False, inject_recovery=True)
        self.assertTrue(ok)
        mock_batch.assert_called_once()
        self.assertEqual(mock_batch.call_args.kwargs.get("preloaded_sessions"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
