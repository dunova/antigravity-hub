#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hub/importer.py - Antigravity Hub 原生账号导入、导出与多格式纳管引擎
===================================================================
【架构铁律】
1. 100% 独立纳管：彻底脱离对任何外部第三方工具或目录的硬依赖；
2. 弹性多格式兼容：支持 Hub 标准备份、字典映射、对象数组、单账号与系统钥匙串吸纳；
3. 安全无损合并：导入时智能更新 Token 与元数据，绝不冲刷本地预热与状态时间戳；
4. 导出原子闭环：支持 Web/CLI 一键全量导出标准备份 JSON。
"""

import os
import sys
import json
import time
import base64
import random
import logging
import subprocess
import urllib.request
import urllib.parse
import ssl
from typing import Dict, Any, List, Optional, Tuple, Union

logger = logging.getLogger("HubImporter")

BASE_DATA_DIR = os.environ.get("ANTIGRAVITY_HUB_DIR", os.path.expanduser("~/.antigravity_hub"))
HUB_DIR = os.path.join(BASE_DATA_DIR, "data")
ACCOUNTS_HUB_FILE = os.path.join(HUB_DIR, "accounts_hub.json")

# Legacy 兼容源（仅作为过渡检测，绝非必须依赖）
LEGACY_TOOLS_DIR = os.path.expanduser("~/.antigravity_tools")
LEGACY_INDEX = os.path.join(LEGACY_TOOLS_DIR, "accounts.json")
LEGACY_DETAILS_DIR = os.path.join(LEGACY_TOOLS_DIR, "accounts")

GOOGLE_ACCOUNTS_PATH = os.path.expanduser("~/.gemini/google_accounts.json")


def _atomic_write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        tmp_path = f"{file_path}.tmp.{os.getpid()}.{time.time()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
        return True
    except Exception as e:
        logger.error(f"原子写入 {file_path} 失败: {e}")
        return False


def normalize_account_record(raw: Dict[str, Any], default_email: str = "") -> Optional[Dict[str, Any]]:
    """
    将任意结构转换为 Hub 规范的 Account 字典。
    必须包含合法 email 和 refresh_token（或 access_token）。
    """
    if not isinstance(raw, dict):
        return None

    email = str(raw.get("email") or default_email or "").strip().lower()
    if not email or "@" not in email:
        return None

    # 提取 Refresh Token 与 Access Token (支持嵌套 token 对象或平铺)
    token_obj = raw.get("token") if isinstance(raw.get("token"), dict) else {}
    refresh_token = str(raw.get("refresh_token") or token_obj.get("refresh_token") or "").strip()
    access_token = str(raw.get("access_token") or token_obj.get("access_token") or "").strip()

    if not refresh_token and not access_token:
        return None

    now_ts = int(time.time())
    tier = str(raw.get("tier") or "PRO").upper()
    name = str(raw.get("name") or email.split("@")[0])

    # 配额对象归一化
    gemini_data = raw.get("gemini", {})
    if not isinstance(gemini_data, dict):
        gemini_data = {}
    claude_data = raw.get("claude", {})
    if not isinstance(claude_data, dict):
        claude_data = {}

    return {
        "email": email,
        "name": name,
        "tier": tier,
        "pro": (tier == "PRO"),
        "refresh_token": refresh_token,
        "access_token": access_token,
        "expiry_timestamp": int(raw.get("expiry_timestamp") or token_obj.get("expiry_timestamp") or (now_ts + 3600)),
        "expires_at": int(raw.get("expires_at") or (now_ts + 3600)),
        "added_at": int(raw.get("added_at") or now_ts),
        "last_refreshed_ts": int(raw.get("last_refreshed_ts") or 0),
        "next_warmup_ts": int(raw.get("next_warmup_ts") or (now_ts + random.randint(300, 1800))),
        "last_warmup_ts": int(raw.get("last_warmup_ts") or 0),
        "validation_blocked": bool(raw.get("validation_blocked", False)),
        "validation_url": raw.get("validation_url") if raw.get("validation_blocked") else None,
        "validation_blocked_reason": raw.get("validation_blocked_reason") if raw.get("validation_blocked") else None,
        "gemini": {
            "quota_5h": float(gemini_data.get("quota_5h", 1.0)),
            "quota_weekly": float(gemini_data.get("quota_weekly", 1.0)),
            "reset_time_5h": str(gemini_data.get("reset_time_5h", "")),
            "reset_time_weekly": str(gemini_data.get("reset_time_weekly", "")),
            "reset_time": str(gemini_data.get("reset_time", ""))
        },
        "claude": {
            "quota_5h": float(claude_data.get("quota_5h", 1.0)),
            "quota_weekly": float(claude_data.get("quota_weekly", 1.0)),
            "reset_time_5h": str(claude_data.get("reset_time_5h", "")),
            "reset_time_weekly": str(claude_data.get("reset_time_weekly", "")),
            "reset_time": str(claude_data.get("reset_time", ""))
        }
    }


def parse_accounts_data(raw_input: Union[str, dict, list]) -> Dict[str, Dict[str, Any]]:
    """
    通用解析器：输入字符串、字典或列表，返回清洗后的 {email: account_record} 映射。
    """
    data = raw_input
    if isinstance(raw_input, str):
        raw_str = raw_input.strip()
        if not raw_str:
            return {}
        try:
            data = json.loads(raw_str)
        except Exception as e:
            logger.error(f"解析 JSON 文本失败: {e}")
            return {}

    parsed_map: Dict[str, Dict[str, Any]] = {}

    # 格式 1: Hub 标准备份包 {"active_email": "...", "accounts": {...}}
    if isinstance(data, dict) and "accounts" in data and isinstance(data["accounts"], dict):
        for email_key, acc_val in data["accounts"].items():
            norm = normalize_account_record(acc_val, default_email=email_key)
            if norm:
                parsed_map[norm["email"]] = norm
        return parsed_map

    # 格式 2: 键为邮箱的字典映射 {"user@gmail.com": {"refresh_token": "..."}}
    if isinstance(data, dict):
        has_emails = any("@" in str(k) for k in data.keys())
        if has_emails:
            for email_key, acc_val in data.items():
                if isinstance(acc_val, dict):
                    norm = normalize_account_record(acc_val, default_email=email_key)
                    if norm:
                        parsed_map[norm["email"]] = norm
            return parsed_map
        elif "email" in data:
            # 格式 4: 单个账号字典 {"email": "...", "refresh_token": "..."}
            norm = normalize_account_record(data)
            if norm:
                parsed_map[norm["email"]] = norm
            return parsed_map

    # 格式 3: 账号对象列表 [{"email": "...", "refresh_token": "..."}, ...]
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                norm = normalize_account_record(item)
                if norm:
                    parsed_map[norm["email"]] = norm
        return parsed_map

    return parsed_map


def import_accounts_payload(payload: Union[str, dict, list], accounts_file: str = ACCOUNTS_HUB_FILE) -> Tuple[bool, int, int, str]:
    """
    批量导入或合并账号：
    返回: (成功状态, 新增数量, 更新数量, 消息文本)
    """
    parsed = parse_accounts_data(payload)
    if not parsed:
        return False, 0, 0, "未能从输入中识别出任何有效的账号凭据（需包含合法 email 与 refresh_token）"

    # 读取现有数据
    hub_data = {"active_email": "", "accounts": {}, "last_updated": int(time.time())}
    if os.path.exists(accounts_file):
        try:
            with open(accounts_file, "r", encoding="utf-8") as f:
                hub_data = json.load(f)
        except Exception:
            pass

    existing_accounts = hub_data.get("accounts", {})
    added_count = 0
    updated_count = 0

    for email, new_rec in parsed.items():
        if email in existing_accounts:
            # 智能更新已有账号凭据与元数据，保留原有的调度与预热进度
            cur = existing_accounts[email]
            if new_rec.get("refresh_token"):
                cur["refresh_token"] = new_rec["refresh_token"]
            if new_rec.get("access_token"):
                cur["access_token"] = new_rec["access_token"]
            if new_rec.get("tier"):
                cur["tier"] = new_rec["tier"]
                cur["pro"] = (new_rec["tier"] == "PRO")
            # 若已有配额为初始占位值 (1.0 且无 reset)，而新导入有真实配额，则更新
            if new_rec.get("gemini", {}).get("reset_time_5h") and not cur.get("gemini", {}).get("reset_time_5h"):
                cur["gemini"] = new_rec["gemini"]
            if new_rec.get("claude", {}).get("reset_time_5h") and not cur.get("claude", {}).get("reset_time_5h"):
                cur["claude"] = new_rec["claude"]
            updated_count += 1
        else:
            # 全新账号
            existing_accounts[email] = new_rec
            added_count += 1

    hub_data["accounts"] = existing_accounts
    if not hub_data.get("active_email") and existing_accounts:
        hub_data["active_email"] = next(iter(existing_accounts.keys()))
    hub_data["last_updated"] = int(time.time())

    ok = _atomic_write_json(accounts_file, hub_data)
    if ok:
        msg = f"成功导入 {added_count + updated_count} 个账号（新增: {added_count}，更新: {updated_count}）"
        logger.info(f"✅ {msg}")
        return True, added_count, updated_count, msg
    else:
        return False, 0, 0, "原子写入账号底表文件失败"


def export_accounts_backup(accounts_file: str = ACCOUNTS_HUB_FILE) -> Dict[str, Any]:
    """
    全量导出当前 Hub 账号池备份 JSON。
    """
    if not os.path.exists(accounts_file):
        return {"version": "v2.27.0", "active_email": "", "accounts": {}, "exported_at": int(time.time())}
    try:
        with open(accounts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["exported_at"] = int(time.time())
        data["version"] = "v2.27.0"
        return data
    except Exception as e:
        logger.error(f"导出账号数据异常: {e}")
        return {"error": str(e), "accounts": {}}


def ingest_system_keychain_or_creds(accounts_file: str = ACCOUNTS_HUB_FILE) -> Tuple[bool, str, str]:
    """
    【从当前 IDE/系统钥匙串一键吸纳】
    检测当前 macOS Keychain 或 Google 凭据中的活跃账号并热纳管。
    返回: (成功状态, email, 消息文本)
    """
    at = ""
    rt = ""
    detected_email = ""

    # 1. 尝试从 macOS Keychain 抓取
    try:
        cmd = ["security", "find-generic-password", "-s", "gemini", "-a", "antigravity", "-w"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout.strip():
            raw = res.stdout.strip()
            if raw.startswith("go-keyring-base64:"):
                raw = raw.replace("go-keyring-base64:", "")
            dec = base64.b64decode(raw).decode("utf-8")
            kd = json.loads(dec)
            at = kd.get("token", {}).get("access_token") or kd.get("access_token") or ""
            rt = kd.get("token", {}).get("refresh_token") or kd.get("refresh_token") or ""
    except Exception:
        pass

    # 2. 探测 Token 所属邮箱
    if at:
        try:
            t_url = f"https://oauth2.googleapis.com/tokeninfo?access_token={at}"
            req = urllib.request.Request(t_url, headers={"User-Agent": "AntigravityHub/2.27"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=3, context=ctx) as r:
                t_info = json.loads(r.read().decode("utf-8"))
                detected_email = t_info.get("email", "").strip().lower()
        except Exception:
            pass

    # 3. 兜底从 ~/.gemini/google_accounts.json 获取
    if not detected_email and os.path.exists(GOOGLE_ACCOUNTS_PATH):
        try:
            with open(GOOGLE_ACCOUNTS_PATH, "r", encoding="utf-8") as f:
                g_acc = json.load(f)
                detected_email = g_acc.get("active", "").strip().lower()
        except Exception:
            pass

    if not detected_email or "@" not in detected_email:
        return False, "", "未在系统钥匙串中探测到有效 Antigravity 登录凭据，请先在 IDE 中完成登录！"

    if not rt and not at:
        return False, detected_email, f"探测到账号 {detected_email}，但未能获取到有效凭据 Token"

    # 组装账号记录并导入
    record = {
        "email": detected_email,
        "tier": "PRO",
        "refresh_token": rt,
        "access_token": at
    }
    ok, added, updated, msg = import_accounts_payload([record], accounts_file=accounts_file)
    if ok:
        action_desc = "新账号纳管入库" if added > 0 else "凭据同步更新"
        return True, detected_email, f"成功从 IDE 钥匙串完成【{action_desc}】: {detected_email}"
    return False, detected_email, msg


def legacy_import_antigravity_tools(accounts_file: str = ACCOUNTS_HUB_FILE) -> bool:
    """
    旧版 ~/.antigravity_tools 单向只读迁移适配器（仅在无数据时作为初始化检测）。
    """
    if not os.path.exists(LEGACY_INDEX):
        return False

    try:
        with open(LEGACY_INDEX, "r", encoding="utf-8") as f:
            ext_idx = json.load(f)
    except Exception:
        return False

    account_ids = ext_idx.get("accounts", [])
    if not account_ids:
        return False

    records = []
    for acc_item in account_ids:
        aid = acc_item.get("id") if isinstance(acc_item, dict) else str(acc_item)
        if not aid:
            continue
        detail_path = os.path.join(LEGACY_DETAILS_DIR, f"{aid}.json")
        if not os.path.exists(detail_path):
            continue
        try:
            with open(detail_path, "r", encoding="utf-8") as df:
                d = json.load(df)
            norm = normalize_account_record(d)
            if norm:
                norm["id"] = aid
                records.append(norm)
        except Exception:
            continue

    if records:
        ok, added, updated, _ = import_accounts_payload(records, accounts_file=accounts_file)
        if ok and ext_idx.get("active_email"):
            # 尝试同步 active_email
            try:
                with open(accounts_file, "r", encoding="utf-8") as f:
                    cur = json.load(f)
                if ext_idx["active_email"] in cur.get("accounts", {}):
                    cur["active_email"] = ext_idx["active_email"]
                    _atomic_write_json(accounts_file, cur)
            except Exception:
                pass
        return ok
    return False


def import_accounts_read_only(accounts_file: str = ACCOUNTS_HUB_FILE) -> bool:
    """
    Hub 首次初始化自检入口：
    1. 优先尝试从 IDE 活跃钥匙串吸纳（零门槛原生自适应）；
    2. 若无钥匙串，检查是否存在 legacy 旧版目录迁移；
    3. 绝不向外部目录回写一字节。
    """
    os.makedirs(os.path.dirname(os.path.abspath(accounts_file)), exist_ok=True)
    if os.path.exists(accounts_file):
        return True

    # 先尝试 Keychain 嗅探
    ok, email, _ = ingest_system_keychain_or_creds(accounts_file=accounts_file)
    if ok:
        logger.info(f"✨ 首次启动自动从系统钥匙串吸纳初始账号: {email}")
        return True

    # 再尝试 Legacy 迁移
    if legacy_import_antigravity_tools(accounts_file=accounts_file):
        logger.info("✨ 首次启动已从旧版数据平滑完成初始化迁移")
        return True

    logger.info("ℹ️ 全新纯净环境初始化完成，当前账号池为空，等待用户添加新账号")
    return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Antigravity Hub 导入导出与纳管 CLI")
    parser.add_argument("--export", type=str, help="导出账号备份到指定 JSON 文件")
    parser.add_argument("--import", dest="import_file", type=str, help="从指定 JSON 文件导入账号")
    parser.add_argument("--sync-active", action="store_true", help="从当前系统钥匙串/IDE 吸纳活跃账号")
    args = parser.parse_args()

    if args.export:
        data = export_accounts_backup()
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ 账号数据已成功导出至: {args.export} (包含 {len(data.get('accounts', {}))} 个账号)")
    elif args.import_file:
        with open(args.import_file, "r", encoding="utf-8") as f:
            content = f.read()
        ok, added, updated, msg = import_accounts_payload(content)
        print(f"{'✅' if ok else '❌'} {msg}")
    elif args.sync_active:
        ok, email, msg = ingest_system_keychain_or_creds()
        print(f"{'✅' if ok else '❌'} {msg}")
    else:
        parser.print_help()
