#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hub/importer.py - Antigravity Hub 只读凭据导入工具
=================================================
【铁律】严格只读单向导入：
仅通过 open(..., 'r') 读取外部 ~/.antigravity_tools 中的凭据与配额结构，
绝对不向外部目录回写一字节！
产物持久化至: $ANTIGRAVITY_HUB_DIR/accounts_hub.json (默认 ~/.antigravity_hub/accounts_hub.json)
"""

import os
import sys
import json
import glob
import time
import logging

logger = logging.getLogger("HubImport")

BASE_DATA_DIR = os.environ.get("ANTIGRAVITY_HUB_DIR", os.path.expanduser("~/.antigravity_hub"))
HUB_ACCOUNTS_FILE = os.path.join(BASE_DATA_DIR, "accounts_hub.json")
EXTERNAL_DIR = os.path.expanduser("~/.antigravity_tools")
EXTERNAL_INDEX = os.path.join(EXTERNAL_DIR, "accounts.json")
EXTERNAL_DETAILS_DIR = os.path.join(EXTERNAL_DIR, "accounts")


def import_accounts_read_only() -> bool:
    os.makedirs(BASE_DATA_DIR, exist_ok=True)

    if not os.path.exists(EXTERNAL_INDEX):
        logger.info(f"外部索引文件不存在: {EXTERNAL_INDEX}，跳过外部导入")
        return False

    try:
        with open(EXTERNAL_INDEX, "r", encoding="utf-8") as f:
            ext_idx = json.load(f)
    except Exception as e:
        logger.error(f"读取外部索引异常: {e}")
        return False

    active_email = ext_idx.get("active_email", "")
    account_ids = ext_idx.get("accounts", [])
    logger.info(f"读取到外部索引包含 {len(account_ids)} 个账号，当前外部活跃账号: {active_email}")

    accounts_map = {}
    for acc_item in account_ids:
        aid = acc_item.get("id") if isinstance(acc_item, dict) else str(acc_item)
        if not aid:
            continue
        detail_path = os.path.join(EXTERNAL_DETAILS_DIR, f"{aid}.json")
        if not os.path.exists(detail_path):
            continue

        try:
            with open(detail_path, "r", encoding="utf-8") as df:
                d = json.load(df)
        except Exception:
            continue

        email = d.get("email")
        if not email:
            continue

        token_obj = d.get("token") or {}
        refresh_token = token_obj.get("refresh_token")
        if not refresh_token:
            continue

        quota_obj = d.get("quota") or {}
        quota_groups = quota_obj.get("quota_groups") or []

        gemini_5h = 1.0
        gemini_weekly = 1.0
        gemini_reset = ""
        gemini_reset_weekly = ""
        claude_5h = 1.0
        claude_weekly = 1.0
        claude_reset = ""
        claude_reset_weekly = ""

        for g in quota_groups:
            g_name = g.get("display_name", "").lower()
            buckets = g.get("buckets", [])
            if "gemini" in g_name:
                for b in buckets:
                    w = b.get("window", "")
                    rem = float(b.get("remaining_fraction", 1.0))
                    if w == "5h":
                        gemini_5h = rem
                        gemini_reset = b.get("reset_time", "")
                    elif w == "weekly":
                        gemini_weekly = rem
                        gemini_reset_weekly = b.get("reset_time", "")
            elif "claude" in g_name or "gpt" in g_name:
                for b in buckets:
                    w = b.get("window", "")
                    rem = float(b.get("remaining_fraction", 1.0))
                    if w == "5h":
                        claude_5h = rem
                        claude_reset = b.get("reset_time", "")
                    elif w == "weekly":
                        claude_weekly = rem
                        claude_reset_weekly = b.get("reset_time", "")

        is_blocked = bool(d.get("validation_blocked", False))
        val_url = d.get("validation_url")
        val_reason = d.get("validation_blocked_reason")

        accounts_map[email] = {
            "id": aid,
            "email": email,
            "name": d.get("name", email.split("@")[0]),
            "tier": d.get("tier", "PRO"),
            "token": token_obj,
            "access_token": token_obj.get("access_token", ""),
            "refresh_token": refresh_token,
            "expiry_timestamp": token_obj.get("expiry_timestamp", 0),
            "validation_blocked": is_blocked,
            "validation_url": val_url,
            "validation_blocked_reason": val_reason,
            "gemini": {
                "quota_5h": gemini_5h,
                "quota_weekly": gemini_weekly,
                "reset_time_5h": gemini_reset,
                "reset_time_weekly": gemini_reset_weekly
            },
            "claude": {
                "quota_5h": claude_5h,
                "quota_weekly": claude_weekly,
                "reset_time_5h": claude_reset,
                "reset_time_weekly": claude_reset_weekly
            }
        }

    hub_data = {
        "active_email": active_email,
        "accounts": accounts_map,
        "last_updated": int(time.time())
    }

    try:
        from core.switcher import atomic_write_json
        atomic_write_json(HUB_ACCOUNTS_FILE, hub_data)
        logger.info(f"✅ 成功完成只读导入，持久化至: {HUB_ACCOUNTS_FILE}")
        return True
    except Exception as e:
        logger.error(f"写入 Hub 账号文件异常: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import_accounts_read_only()
