#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity Hub - 独立容器 OAuth 极速授权 CLI
用法:
  python3 hub/oauth_cli.py
自动调用 Hub 并在全新隔离沙盒中弹出浏览器登录授权，杜绝串号。
"""
import sys
import os
import json
import time
import urllib.request
import urllib.parse

HUB_URL = os.environ.get("HUB_URL", "http://127.0.0.1:18088")

def main():
    print("=" * 60)
    print("🚀 Antigravity Hub - 独立沙盒 OAuth 授权助手")
    print("=" * 60)

    # 1. 请求 Hub 启动独立容器授权
    req_data = json.dumps({"isolated": True, "open_browser": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{HUB_URL}/api/oauth/start",
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ 连接 Hub 服务失败 ({HUB_URL}): {e}")
        print("请确认 antigravity-hub.service 正在运行！")
        sys.exit(1)

    if data.get("status") != "ok":
        print(f"❌ 启动授权异常: {data.get('message')}")
        sys.exit(1)

    state = data["state"]
    auth_url = data["auth_url"]
    print(f"🛡️ 已拉起独立沙盒浏览器窗口！")
    print(f"👉 授权 State: {state}")
    print(f"🔗 若窗口未自动弹出，请复制此链接在任意浏览器中打开登录授权：\n{auth_url}\n")
    print("⏳ 正在等待 Google 登录授权回调...")

    # 2. 轮询状态
    start_time = time.time()
    while time.time() - start_time < 300:
        time.sleep(1.5)
        try:
            poll_req = urllib.request.Request(f"{HUB_URL}/api/oauth/poll?state={urllib.parse.quote(state)}")
            with urllib.request.urlopen(poll_req, timeout=5) as p_resp:
                p_data = json.loads(p_resp.read().decode("utf-8"))
                status = p_data.get("status")
                if status == "success":
                    email = p_data.get("email", "")
                    msg = p_data.get("message", "")
                    print("\n" + "=" * 60)
                    print(f"🎉 授权成功！账号已自动纳管入库: {email}")
                    print(f"📄 详情: {msg}")
                    print("=" * 60)
                    return
                elif status == "error":
                    print(f"\n❌ 授权失败: {p_data.get('message')}")
                    return
                else:
                    print(".", end="", flush=True)
        except Exception:
            pass

    print("\n⚠️ 授权等待超时 (5分钟)，请重试。")

if __name__ == "__main__":
    main()
