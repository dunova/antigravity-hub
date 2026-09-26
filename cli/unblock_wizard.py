#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cli/unblock_wizard.py - Antigravity 账号隔离解封向导与自动监听中枢
=================================================================
核心能力：
1. 自动续签过期 OAuth access_token，彻底消除因 401 导致的假死误判；
2. 实时向官方接口获取最新未过期的 validation_url (带动态 plt 令牌)；
3. 自动封装为 Google AccountChooser 智能定向链接，彻底杜绝 500 串号错误；
4. 支持一键通过 Chrome / Brave 隔离 Profile 容器打开，会话 100% 独立；
5. 后台自动监听解封进度，一旦网页验证通过，毫秒级自动清除本地与 Hub 风控标记。
"""

import os
import sys
import json
import time
import glob
import ssl
import urllib.request
import urllib.parse
import subprocess
from typing import Dict, Any, List, Optional, Tuple

# 导入核心模块
try:
    from core.switcher import (
        AntigravityPhysicalManager,
        BASE_DATA_DIR,
        ACCOUNTS_HUB_FILE,
        ANTIGRAVITY_TOOLS_ACCOUNTS_DIR,
        NATIVE_OAUTH_USER_AGENT,
        atomic_write_json,
        _safe_decode_resp
    )
except ImportError:
    # 兼容脚本直接独立执行
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.switcher import (
        AntigravityPhysicalManager,
        BASE_DATA_DIR,
        ACCOUNTS_HUB_FILE,
        ANTIGRAVITY_TOOLS_ACCOUNTS_DIR,
        NATIVE_OAUTH_USER_AGENT,
        atomic_write_json,
        _safe_decode_resp
    )

QUOTA_SUMMARY_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
PROFILES_BASE_DIR = os.path.join(BASE_DATA_DIR, "browser_profiles")


def get_blocked_accounts() -> List[Dict[str, Any]]:
    """扫描所有被标记为 validation_blocked 的账号，并自动确保 access_token 新鲜有效"""
    mgr = AntigravityPhysicalManager()
    blocked = []

    # 1. 扫描 Hub 数据库
    hub_data = mgr.load_hub_accounts()
    for email, d in hub_data.get("accounts", {}).items():
        if d.get("validation_blocked"):
            tok = d.get("token", {})
            acc_obj = {
                "email": email,
                "access_token": tok.get("access_token") or d.get("access_token", ""),
                "refresh_token": tok.get("refresh_token") or d.get("refresh_token", ""),
                "expiry_timestamp": tok.get("expiry_timestamp") or d.get("expiry_timestamp", 0)
            }
            at, _ = mgr.ensure_fresh_token(acc_obj)
            blocked.append({
                "source": "hub",
                "email": email,
                "name": d.get("name", email),
                "access_token": at or acc_obj["access_token"],
                "cached_val_url": d.get("validation_url", "")
            })

    # 2. 扫描外部工具账号目录（若存在）
    if os.path.exists(ANTIGRAVITY_TOOLS_ACCOUNTS_DIR):
        for p in sorted(glob.glob(os.path.join(ANTIGRAVITY_TOOLS_ACCOUNTS_DIR, "*.json"))):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                email = d.get("email", "")
                if d.get("validation_blocked") and not any(b["email"] == email for b in blocked):
                    tok = d.get("token", {})
                    acc_obj = {
                        "id": os.path.basename(p).replace(".json", ""),
                        "email": email,
                        "refresh_token": tok.get("refresh_token", ""),
                        "access_token": tok.get("access_token", ""),
                        "expiry_timestamp": tok.get("expiry_timestamp", 0)
                    }
                    at, _ = mgr.ensure_fresh_token(acc_obj)
                    blocked.append({
                        "source": "antigravity_tools",
                        "file_path": p,
                        "email": email,
                        "name": d.get("name", email),
                        "access_token": at or acc_obj["access_token"],
                        "cached_val_url": d.get("validation_url", "")
                    })
            except Exception:
                pass

    return blocked


def fetch_fresh_validation_url(access_token: str) -> Tuple[bool, str]:
    """
    轻量嗅探 Google 配额接口：
    若已解封 -> 返回 (True, "")
    若仍拦截 -> 实时提取最新、未过期的 validation_url (含动态 plt 令牌)
    """
    if not access_token:
        return False, ""

    req = urllib.request.Request(
        QUOTA_SUMMARY_ENDPOINT,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": NATIVE_OAUTH_USER_AGENT
        },
        method="POST",
        data=b"{}"
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
            return True, ""
    except urllib.error.HTTPError as e:
        if e.code == 403:
            body = _safe_decode_resp(e.read())
            try:
                j = json.loads(body)
                for det in j.get("error", {}).get("details", []):
                    if det.get("reason") == "VALIDATION_REQUIRED":
                        url = det.get("metadata", {}).get("validation_url", "")
                        if url:
                            return False, url
            except Exception:
                pass
        return False, ""
    except Exception:
        return False, ""


def make_smart_chooser_url(email: str, raw_url: str) -> str:
    """
    封装为 Google AccountChooser 定向路由链接：
    1. 自动携带 Email 与 authuser 参数，强制浏览器切换到目标账号上下文；
    2. 彻底杜绝多账号登录 Cookie 错位导致的 500 报错。
    """
    if "&authuser" in raw_url:
        fixed_raw = raw_url.replace("&authuser", f"&authuser={urllib.parse.quote(email)}")
    else:
        fixed_raw = f"{raw_url}&authuser={urllib.parse.quote(email)}"

    return f"https://accounts.google.com/AccountChooser?Email={urllib.parse.quote(email)}&continue={urllib.parse.quote(fixed_raw)}"


def launch_isolated_browser(email: str, target_url: str, browser: str = "Google Chrome") -> bool:
    """使用隔离的用户数据目录拉起全新浏览器窗口，确保 Cookie 100% 独立不串号"""
    safe_name = email.replace("@", "_").replace(".", "_")
    profile_dir = os.path.join(PROFILES_BASE_DIR, safe_name)
    os.makedirs(profile_dir, exist_ok=True)

    if sys.platform == "darwin":
        app_name = "Google Chrome" if browser == "Google Chrome" else "Brave Browser"
        cmd = [
            "open", "-na", app_name,
            "--args",
            f"--user-data-dir={profile_dir}",
            target_url
        ]
    else:
        # Linux
        bin_name = "google-chrome" if browser == "Google Chrome" else "brave-browser"
        cmd = [
            bin_name,
            f"--user-data-dir={profile_dir}",
            target_url
        ]

    try:
        subprocess.Popen(cmd)
        return True
    except Exception as e:
        print(f"❌ 启动独立浏览器失败: {e}")
        return False


def clear_account_block_state(acc_dict: Dict[str, Any]):
    """解封成功：原子清除本地 json 与 Hub 状态"""
    email = acc_dict["email"]
    mgr = AntigravityPhysicalManager()

    # 1. 清除 Hub 数据库状态
    try:
        hub_data = mgr.load_hub_accounts()
        if email in hub_data.get("accounts", {}):
            hub_data["accounts"][email]["validation_blocked"] = False
            hub_data["accounts"][email]["validation_url"] = None
            hub_data["accounts"][email]["validation_blocked_reason"] = None
            mgr.save_hub_accounts(hub_data)
            print(f"🎉 账号 {email} Hub 风控标记已成功清除！")
    except Exception as e:
        print(f"❌ 清除 Hub 状态异常: {e}")

    # 2. 清除外部文件状态（若存在）
    fp = acc_dict.get("file_path")
    if fp and os.path.exists(fp):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                d = json.load(f)
            d["validation_blocked"] = False
            d["validation_url"] = None
            d["validation_blocked_reason"] = None
            atomic_write_json(fp, d)
            print(f"🎉 账号 {email} 本地配置文件风控标记已成功物理清除！")
        except Exception as e:
            print(f"❌ 清除文件风控标记异常: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Antigravity 账号隔离解封向导")
    parser.add_argument("--list", action="store_true", help="列出所有需验证账号与智能防 500 链接")
    parser.add_argument("--open", type=str, help="使用隔离浏览器打开指定邮箱的解封向导")
    parser.add_argument("--open-all", action="store_true", help="依次打开所有待解封账号的隔离窗口")
    parser.add_argument("--watch", action="store_true", help="常驻监听模式：自动检测解封并毫秒级恢复账号")
    parser.add_argument("--browser", type=str, default="Google Chrome", choices=["Google Chrome", "Brave Browser"], help="使用的浏览器")
    args = parser.parse_args()

    blocked = get_blocked_accounts()
    if not blocked:
        print("✅ 全池所有账号状态健康，当前无任何账号处于风控拦截态！")
        return

    print(f"🔍 发现 {len(blocked)} 个账号当前处于拦截/需验证态：\n")

    if args.list or (not args.open and not args.open_all and not args.watch):
        for idx, acc in enumerate(blocked, 1):
            email = acc["email"]
            at = acc["access_token"]
            is_ok, fresh_url = fetch_fresh_validation_url(at)
            if is_ok:
                print(f"[{idx}] {email} -> 🌟 恭喜！Google 云端已恢复健康，正在自动解锁...")
                clear_account_block_state(acc)
                continue

            target_url = fresh_url or acc["cached_val_url"]
            smart_url = make_smart_chooser_url(email, target_url) if target_url else "未能获取解封链接"

            print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"📌 [{idx}] 目标账号: {email} ({acc['name']})")
            print(f"🔗 智能防 500 解封链接:\n{smart_url}")
            print(f"🚀 一键隔离启动命令:\npython3 cli/unblock_wizard.py --open {email}")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        print("💡 提示：运行 `python3 cli/unblock_wizard.py --watch` 可启动后台常驻监听，完成网页验证后系统自动解锁并同步入池！")

    if args.open:
        target = args.open.strip().lower()
        matched = [a for a in blocked if a["email"].lower() == target]
        if not matched:
            print(f"❌ 未找到处于拦截态的账号: {target}")
            return
        acc = matched[0]
        is_ok, fresh_url = fetch_fresh_validation_url(acc["access_token"])
        if is_ok:
            print(f"🎉 账号 {acc['email']} 云端已恢复健康，直接自动解锁！")
            clear_account_block_state(acc)
            return
        target_url = fresh_url or acc["cached_val_url"]
        smart_url = make_smart_chooser_url(acc["email"], target_url)
        print(f"🚀 正在为 {acc['email']} 启动专属无污染独立浏览器 Profile 窗口...")
        launch_isolated_browser(acc["email"], smart_url, browser=args.browser)
        print("✅ 独立窗口已拉起！请在窗口中登录该账号并点击确认。")
        print("👀 启动后台快速轮询监听该账号状态...")
        for _ in range(60):
            time.sleep(3)
            is_ok, _ = fetch_fresh_validation_url(acc["access_token"])
            if is_ok:
                print(f"🎉🎉 检测到账号 {acc['email']} 已经成功解封！自动恢复账号！")
                clear_account_block_state(acc)
                return
        print("⏳ 监听超时，稍后可运行 --watch 统一检测。")

    if args.open_all:
        for acc in blocked:
            is_ok, fresh_url = fetch_fresh_validation_url(acc["access_token"])
            if is_ok:
                clear_account_block_state(acc)
                continue
            target_url = fresh_url or acc["cached_val_url"]
            smart_url = make_smart_chooser_url(acc["email"], target_url)
            print(f"🚀 拉起 {acc['email']} 隔离窗口...")
            launch_isolated_browser(acc["email"], smart_url, browser=args.browser)
            time.sleep(1.5)

    if args.watch:
        print("🛡️ 启动自动解封常驻监听器 (每 5 秒轮询一次)... 按 Ctrl+C 退出")
        while True:
            current_blocked = get_blocked_accounts()
            if not current_blocked:
                print("🎉 所有账号已全部解封，全池满血归位！")
                break
            for acc in current_blocked:
                is_ok, _ = fetch_fresh_validation_url(acc["access_token"])
                if is_ok:
                    print(f"🎉 检测到账号 {acc['email']} 已验证解封，立即清除拦截标记！")
                    clear_account_block_state(acc)
            time.sleep(5)


if __name__ == "__main__":
    main()
