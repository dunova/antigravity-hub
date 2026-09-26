#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/render_mock_preview.py - 生成带 15 个虚拟账号的高密看板 UI 静态预览
======================================================================
用于无凭据沙盒环境下的前端渲染测试、视觉审计与文档截图自动生成。
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import hub.server as hs

mock_accounts = {
    "alex.dev@corp.internal": {
        "email": "alex.dev@corp.internal",
        "name": "alex.dev",
        "tier": "PRO",
        "refresh_token": "mock_rt_1",
        "access_token": "mock_at_1",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.924, "quota_weekly": 0.880, "reset_time_5h": "已就绪", "reset_time_weekly": "4d 12h"},
        "claude": {"quota_5h": 0.950, "quota_weekly": 0.912, "reset_time_5h": "已就绪", "reset_time_weekly": "4d 12h"}
    },
    "core.lead@ai-lab.io": {
        "email": "core.lead@ai-lab.io",
        "name": "core.lead",
        "tier": "PRO",
        "refresh_token": "mock_rt_2",
        "access_token": "mock_at_2",
        "validation_blocked": False,
        "gemini": {"quota_5h": 1.0, "quota_weekly": 0.965, "reset_time_5h": "已就绪", "reset_time_weekly": "5d 08h"},
        "claude": {"quota_5h": 1.0, "quota_weekly": 0.940, "reset_time_5h": "已就绪", "reset_time_weekly": "5d 08h"}
    },
    "sarah.infra@cloud.net": {
        "email": "sarah.infra@cloud.net",
        "name": "sarah.infra",
        "tier": "PRO",
        "refresh_token": "mock_rt_3",
        "access_token": "mock_at_3",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.742, "quota_weekly": 0.820, "reset_time_5h": "1h 15m", "reset_time_weekly": "3d 14h"},
        "claude": {"quota_5h": 0.680, "quota_weekly": 0.850, "reset_time_5h": "1h 15m", "reset_time_weekly": "3d 14h"}
    },
    "subagent.pool.01@agent.org": {
        "email": "subagent.pool.01@agent.org",
        "name": "subagent.pool.01",
        "tier": "PRO",
        "refresh_token": "mock_rt_4",
        "access_token": "mock_at_4",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.550, "quota_weekly": 0.705, "reset_time_5h": "2h 40m", "reset_time_weekly": "2d 18h"},
        "claude": {"quota_5h": 0.620, "quota_weekly": 0.760, "reset_time_5h": "2h 40m", "reset_time_weekly": "2d 18h"}
    },
    "quantum.opt@matrix.ai": {
        "email": "quantum.opt@matrix.ai",
        "name": "quantum.opt",
        "tier": "PRO",
        "refresh_token": "mock_rt_5",
        "access_token": "mock_at_5",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.385, "quota_weekly": 0.640, "reset_time_5h": "3h 10m", "reset_time_weekly": "1d 22h"},
        "claude": {"quota_5h": 0.420, "quota_weekly": 0.680, "reset_time_5h": "3h 10m", "reset_time_weekly": "1d 22h"}
    },
    "vector.search@cluster.io": {
        "email": "vector.search@cluster.io",
        "name": "vector.search",
        "tier": "PRO",
        "refresh_token": "mock_rt_6",
        "access_token": "mock_at_6",
        "validation_blocked": True,
        "validation_url": "https://accounts.google.com/signin/v2/challenge/pwd",
        "gemini": {"quota_5h": 0.150, "quota_weekly": 0.520, "reset_time_5h": "3h 55m", "reset_time_weekly": "2d 06h"},
        "claude": {"quota_5h": 0.180, "quota_weekly": 0.550, "reset_time_5h": "3h 55m", "reset_time_weekly": "2d 06h"}
    },
    "pipeline.runner@ci-cd.org": {
        "email": "pipeline.runner@ci-cd.org",
        "name": "pipeline.runner",
        "tier": "PRO",
        "refresh_token": "mock_rt_7",
        "access_token": "mock_at_7",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.880, "quota_weekly": 0.840, "reset_time_5h": "已就绪", "reset_time_weekly": "4d 02h"},
        "claude": {"quota_5h": 0.900, "quota_weekly": 0.865, "reset_time_5h": "已就绪", "reset_time_weekly": "4d 02h"}
    },
    "deep.thinker@research.net": {
        "email": "deep.thinker@research.net",
        "name": "deep.thinker",
        "tier": "PRO",
        "refresh_token": "mock_rt_8",
        "access_token": "mock_at_8",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.650, "quota_weekly": 0.750, "reset_time_5h": "1h 55m", "reset_time_weekly": "3d 09h"},
        "claude": {"quota_5h": 0.580, "quota_weekly": 0.720, "reset_time_5h": "1h 55m", "reset_time_weekly": "3d 09h"}
    },
    "kernel.daemon@system.io": {
        "email": "kernel.daemon@system.io",
        "name": "kernel.daemon",
        "tier": "PRO",
        "refresh_token": "mock_rt_9",
        "access_token": "mock_at_9",
        "validation_blocked": False,
        "gemini": {"quota_5h": 1.0, "quota_weekly": 0.920, "reset_time_5h": "已就绪", "reset_time_weekly": "5d 16h"},
        "claude": {"quota_5h": 0.960, "quota_weekly": 0.890, "reset_time_5h": "已就绪", "reset_time_weekly": "5d 16h"}
    },
    "vision.multimodal@ai-lab.io": {
        "email": "vision.multimodal@ai-lab.io",
        "name": "vision.multimodal",
        "tier": "PRO",
        "refresh_token": "mock_rt_10",
        "access_token": "mock_at_10",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.480, "quota_weekly": 0.600, "reset_time_5h": "2h 20m", "reset_time_weekly": "1d 15h"},
        "claude": {"quota_5h": 0.520, "quota_weekly": 0.650, "reset_time_5h": "2h 20m", "reset_time_weekly": "1d 15h"}
    },
    "teamwork.sync@collab.net": {
        "email": "teamwork.sync@collab.net",
        "name": "teamwork.sync",
        "tier": "PRO",
        "refresh_token": "mock_rt_11",
        "access_token": "mock_at_11",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.820, "quota_weekly": 0.790, "reset_time_5h": "已就绪", "reset_time_weekly": "4d 20h"},
        "claude": {"quota_5h": 0.850, "quota_weekly": 0.810, "reset_time_5h": "已就绪", "reset_time_weekly": "4d 20h"}
    },
    "benchmark.suite@perf.org": {
        "email": "benchmark.suite@perf.org",
        "name": "benchmark.suite",
        "tier": "PRO",
        "refresh_token": "mock_rt_12",
        "access_token": "mock_at_12",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.250, "quota_weekly": 0.450, "reset_time_5h": "4h 05m", "reset_time_weekly": "1d 04h"},
        "claude": {"quota_5h": 0.300, "quota_weekly": 0.480, "reset_time_5h": "4h 05m", "reset_time_weekly": "1d 04h"}
    },
    "audit.guardian@sec.io": {
        "email": "audit.guardian@sec.io",
        "name": "audit.guardian",
        "tier": "PRO",
        "refresh_token": "mock_rt_13",
        "access_token": "mock_at_13",
        "validation_blocked": False,
        "gemini": {"quota_5h": 1.0, "quota_weekly": 0.980, "reset_time_5h": "已就绪", "reset_time_weekly": "6d 10h"},
        "claude": {"quota_5h": 1.0, "quota_weekly": 0.975, "reset_time_5h": "已就绪", "reset_time_weekly": "6d 10h"}
    },
    "token.arbiter@quota.net": {
        "email": "token.arbiter@quota.net",
        "name": "token.arbiter",
        "tier": "PRO",
        "refresh_token": "mock_rt_14",
        "access_token": "mock_at_14",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.120, "quota_weekly": 0.380, "reset_time_5h": "3h 50m", "reset_time_weekly": "18h 30m"},
        "claude": {"quota_5h": 0.150, "quota_weekly": 0.400, "reset_time_5h": "3h 50m", "reset_time_weekly": "18h 30m"}
    },
    "fallback.standby@backup.org": {
        "email": "fallback.standby@backup.org",
        "name": "fallback.standby",
        "tier": "PRO",
        "refresh_token": "mock_rt_15",
        "access_token": "mock_at_15",
        "validation_blocked": False,
        "gemini": {"quota_5h": 0.0, "quota_weekly": 0.0, "reset_time_5h": "周枯竭", "reset_time_weekly": "2d 05h"},
        "claude": {"quota_5h": 0.0, "quota_weekly": 0.0, "reset_time_5h": "周枯竭", "reset_time_weekly": "2d 05h"}
    }
}

mock_data = {
    "active_email": "alex.dev@corp.internal",
    "accounts": mock_accounts,
    "last_updated": int(time.time())
}

hs.ENGINE.load_accounts = lambda: mock_data
hs.get_manual_override_lock = lambda: None

output_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "preview.html"))
os.makedirs(os.path.dirname(output_path), exist_ok=True)

html = hs.render_dashboard_html()
with open(output_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"✅ 成功生成 15 账号测试页面: {output_path}")
