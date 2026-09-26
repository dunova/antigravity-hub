#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
start_hub.py - Antigravity Hub 一键启动入口
===========================================
支持一键拉起 Neo-Brutalism + HTMX 高密管理看板与后台配额看门狗守护。

用法:
    python3 start_hub.py [--port 18088] [--data-dir ~/.antigravity_hub] [--no-rotator] [--open-browser]
"""

import os
import sys
import time
import argparse
import threading
import logging
import webbrowser

# 将当前目录加入模块搜索路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hub.server import run_server
from core.rotator import AntigravityQuotaRotator
from core.switcher import BASE_DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [AntigravityHub] %(message)s"
)
logger = logging.getLogger("AntigravityHub")


def main():
    parser = argparse.ArgumentParser(description="Antigravity Hub 一键启动器")
    parser.add_argument("--port", type=int, default=18088, help="Web 看板监听端口 (默认: 18088)")
    parser.add_argument("--data-dir", type=str, default=BASE_DATA_DIR, help="数据存储目录 (默认: ~/.antigravity_hub)")
    parser.add_argument("--no-rotator", action="store_true", help="不启动后台配额看门狗守护线程")
    parser.add_argument("--open-browser", action="store_true", help="启动后自动打开浏览器访问看板")
    args = parser.parse_args()

    os.environ["ANTIGRAVITY_HUB_DIR"] = os.path.abspath(os.path.expanduser(args.data_dir))
    os.makedirs(os.environ["ANTIGRAVITY_HUB_DIR"], exist_ok=True)

    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║               🚀  A N T I G R A V I T Y  H U B            ║
    ║             多账号无感轮换 · 零风控配额看门狗守护中枢             ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    print(banner)
    logger.info(f"📁 数据存储基准目录: {os.environ['ANTIGRAVITY_HUB_DIR']}")

    # 1. 启动后台配额看门狗 (可选)
    if not args.no_rotator:
        def rotator_worker():
            rotator = AntigravityQuotaRotator(check_interval=60, data_dir=os.environ["ANTIGRAVITY_HUB_DIR"])
            rotator.run_daemon()

        t_rot = threading.Thread(target=rotator_worker, daemon=True)
        t_rot.start()
        logger.info("🛡️ 后台 5 小时配额看门狗守护线程已成功就绪")

    # 2. 自动打开浏览器
    if args.open_browser:
        def open_browser():
            time.sleep(1.0)
            url = f"http://127.0.0.1:{args.port}"
            logger.info(f"🌐 正在自动打开浏览器: {url}")
            webbrowser.open(url)

        threading.Thread(target=open_browser, daemon=True).start()

    # 3. 启动 Web 控制台
    logger.info(f"🌟 Web 管理看板启动中: http://127.0.0.1:{args.port}")
    run_server(port=args.port)


if __name__ == "__main__":
    main()
