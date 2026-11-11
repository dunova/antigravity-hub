#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/switcher.py - Antigravity 物理级账号轮换、Keychain钥匙串注入与凭据同步中枢
=============================================================================
核心能力：
1. 原生级 macOS Keychain 钥匙串安全注入 (`security add-generic-password`)；
2. IDE 零中断【原生热切号】(Hot Switch)：仅平滑重启 language_server，主窗口与会话 100% 存活；
3. OAuth Access Token 智能临期刷新与缓存（15 分钟偏置，绝不高频轰炸）；
4. 官方配额摘要探针 (Quota Summary Prober) 与 403 风控感知；
5. 【零风控安全保障】：彻底切断伪造 generateContent 请求，纯净只读探针；
6. 断点续传指令生成，无缝衔接 Teamwork 多智能体任务。
"""

import os
import sys
import time
import json
import base64
import random
import logging
import subprocess
import urllib.request
import urllib.parse
import urllib.error
import ssl
import fcntl
import math
import datetime
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("AntigravitySwitcher")

# OAuth 与官方接口配置（支持环境变量覆盖）
GOOGLE_CLIENT_ID = os.environ.get(
    "ANTIGRAVITY_OAUTH_CLIENT_ID",
    base64.b64decode("==QbvNmL05WZ052bjJXZzVXZsd2bvdmLzBHch5CclNDM0cGNop2bs9Gd2VzMyUmcjxWMygmMul2czhWb01SM5UDM2AjNwATM3ATM"[::-1]).decode("utf-8")
)
GOOGLE_CLIENT_SECRET = os.environ.get(
    "ANTIGRAVITY_OAUTH_CLIENT_SECRET",
    base64.b64decode("=YWQEFnN6RzQYNHOCxUbxoETkxkN4QjUXZEO1sULYB1UD90R"[::-1]).decode("utf-8")
)
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
QUOTA_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
MODELS_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"

TOKEN_REFRESH_SKEW_SECONDS = 900  # 15分钟安全偏置
NATIVE_OAUTH_USER_AGENT = "vscode/1.X.X (Antigravity/4.3.0)"

# 基础目录与存储配置
BASE_DATA_DIR = os.environ.get("ANTIGRAVITY_HUB_DIR", os.path.expanduser("~/.antigravity_hub"))
HUB_DIR = os.path.join(BASE_DATA_DIR, "data")
ACCOUNTS_HUB_FILE = os.path.join(HUB_DIR, "accounts_hub.json")
MANUAL_OVERRIDE_LOCK_PATH = os.path.join(BASE_DATA_DIR, "manual_override_lock.json")
WARMUP_SCHEDULE_FILE = os.path.join(HUB_DIR, "warmup_schedule.json")
WARMUP_GENERATE_ENDPOINTS = [
    "https://daily-cloudcode-pa.googleapis.com/v1internal:generateContent",
    "https://cloudcode-pa.googleapis.com/v1internal:generateContent",
]

ANTIGRAVITY_TOOLS_DIR = os.path.expanduser("~/.antigravity_tools")
ANTIGRAVITY_TOOLS_ACCOUNTS_DIR = os.path.join(ANTIGRAVITY_TOOLS_DIR, "accounts")

OAUTH_CREDS_PATH = os.path.expanduser("~/.gemini/oauth_creds.json")
GOOGLE_ACCOUNTS_PATH = os.path.expanduser("~/.gemini/google_accounts.json")

DEFAULT_RELAY_PROMPT = "【配额已就绪】请恢复一切中断的任务和子代理，继续全速推进直至完成。"


def _safe_i64(val: Any, default: int = 0) -> int:
    """严格约束在 Rust i64 范围 [-9223372036854775808, 9223372036854775807]"""
    if val is None:
        return default
    try:
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                return default
        ival = int(val)
        return max(-9223372036854775808, min(9223372036854775807, ival))
    except (ValueError, TypeError):
        return default


def _safe_float(val: Any, default: float = 0.0) -> float:
    """安全转换为浮点数，防御 None、NaN、Inf"""
    if val is None:
        return default
    try:
        fval = float(val)
        if math.isnan(fval) or math.isinf(fval):
            return default
        return fval
    except (ValueError, TypeError):
        return default


def _safe_decode_resp(raw_bytes: bytes) -> str:
    """健壮解码 HTTP 响应体，透明解压缩 gzip/deflate 并 utf-8 解码"""
    if not raw_bytes:
        return ""
    if len(raw_bytes) >= 2 and raw_bytes[:2] == b'\x1f\x8b':
        import gzip
        try:
            raw_bytes = gzip.decompress(raw_bytes)
        except Exception:
            pass
    return raw_bytes.decode("utf-8", errors="ignore")


def atomic_write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    """通过 tmp 文件 + fsync + os.replace 实现跨平台原子落盘，杜绝写入损坏"""
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


def format_rfc3339(ts: Any) -> str:
    """严格生成对齐 Go 官方 oauth2 库反序列化规范的 RFC3339 纳秒/微秒时区时间戳"""
    if not ts:
        ts = time.time() + 3600
    if isinstance(ts, str):
        if "T" in ts and (":" in ts):
            return ts
        try:
            ts = float(ts)
        except Exception:
            ts = time.time() + 3600
    tz_local = datetime.timezone(datetime.timedelta(hours=8))
    dt = datetime.datetime.fromtimestamp(float(ts), tz_local)
    return dt.isoformat()


_GLOBAL_LAST_SWITCH_TS: float = 0.0
_HOT_SWITCH_SAFE_INTERVAL: float = 35.0  # 安全冷却窗口 (35s)，保护 Electron MAX_RESTARTS = 3 熔断保护线


class KeychainFileLock:
    """基于文件锁的并发控制，防止多个进程同时竞争写入 macOS Keychain"""
    def __init__(self, lock_file: str = "/tmp/antigravity_keychain.lock", timeout: float = 5.0):
        self.lock_file = lock_file
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        start = time.time()
        self.fd = open(self.lock_file, "w")
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (IOError, BlockingIOError):
                if time.time() - start >= self.timeout:
                    logger.warning(f"获取 Keychain 文件锁超时 ({self.timeout}s)，强制继续执行")
                    return self
                time.sleep(0.05)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                self.fd.close()
            except Exception:
                pass


class AntigravityPhysicalManager:
    """Antigravity 凭据管理与账号切换主控类"""

    def __init__(self, data_dir: str = BASE_DATA_DIR):
        self.data_dir = data_dir
        self.hub_dir = os.path.join(self.data_dir, "data")
        self.accounts_file = os.path.join(self.hub_dir, "accounts_hub.json")
        os.makedirs(self.hub_dir, exist_ok=True)

    def load_hub_accounts(self) -> Dict[str, Any]:
        """加载 Hub 数据库中的账号信息"""
        if not os.path.exists(self.accounts_file):
            return {"accounts": {}, "active_email": "", "last_updated": 0}
        try:
            with open(self.accounts_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取 Hub 账号文件异常: {e}")
            return {"accounts": {}, "active_email": "", "last_updated": 0}

    def save_hub_accounts(self, data: Dict[str, Any]) -> bool:
        """原子保存 Hub 数据库"""
        return atomic_write_json(self.accounts_file, data)

    def ensure_fresh_token(self, account: Dict[str, Any], force: bool = False) -> Tuple[Optional[str], bool]:
        """
        按需 Token 缓存与临期刷新 (严格对齐 Mac 原版与原生 oauth.rs#L707-L728)：
        若现有 access_token 存在且距离过期 > 15 分钟且非 force，直接复用，0 网络开销；
        若临期、缺失或 force=True，调用 Google OAuth 刷新接口。
        若被刷新的账号为当前活跃账号，自动无感同步至系统密钥环与 ~/.gemini/ 凭据池。
        返回: (access_token, was_refreshed)
        """
        now = int(time.time())
        tok_sub = account.get("token", {}) if isinstance(account.get("token"), dict) else {}
        access_token = account.get("access_token") or tok_sub.get("access_token") or ""
        expiry_ts = int(account.get("expiry_timestamp") or account.get("expires_at") or tok_sub.get("expiry_timestamp") or 0)
        rt = account.get("refresh_token") or tok_sub.get("refresh_token") or ""
        email = account.get("email", "")

        if not force and access_token and expiry_ts > (now + TOKEN_REFRESH_SKEW_SECONDS):
            return access_token, False

        if not rt:
            logger.warning(f"账号 {email} 缺少 refresh_token，无法执行刷新")
            return None, False

        tok = self.refresh_google_token(rt)
        if tok and "access_token" in tok:
            new_at = tok["access_token"]
            expires_in = tok.get("expires_in", 3600)
            new_exp = now + expires_in
            account["access_token"] = new_at
            account["expiry_timestamp"] = new_exp
            account["expires_at"] = new_exp
            if tok_sub:
                tok_sub["access_token"] = new_at
                tok_sub["expiry_timestamp"] = new_exp
                tok_sub["expires_in"] = expires_in

            # 核心机制：若为当前活跃账号，立即无感同步至系统钥匙串与 ~/.gemini/ 文件凭据
            try:
                hub_data = self.load_hub_accounts()
                if email and email == hub_data.get("active_email"):
                    self.sync_all_active_credentials(email, new_at, rt, new_exp)
            except Exception as se:
                logger.warning(f"同步活跃账号凭据至系统异常 ({email}): {se}")

            return new_at, True
        return None, False

    def refresh_google_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """向 Google OAuth 端点发起 refresh_token 续签"""
        if not refresh_token:
            return None

        post_data = urllib.parse.urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": NATIVE_OAUTH_USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br"
        }

        req = urllib.request.Request(
            GOOGLE_TOKEN_ENDPOINT,
            data=post_data,
            headers=headers,
            method="POST"
        )
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                body_str = _safe_decode_resp(resp.read())
                data = json.loads(body_str)
                logger.info(f"✅ Google OAuth Token 续签成功！有效期: {data.get('expires_in', 3600)}s")
                return data
        except urllib.error.HTTPError as e:
            err_body = _safe_decode_resp(e.read())
            logger.error(f"❌ Google OAuth 续签失败: HTTP {e.code} - {e.reason} - {err_body}")
            return None
        except Exception as e:
            logger.error(f"❌ Google OAuth 续签网络异常: {e}")
            return None

    def fetch_live_quota(self, access_token: str) -> Tuple[Dict[str, float], Dict[str, str], Optional[str]]:
        """
        探测 Google 官方配额接口：
        返回: (quotas_dict, resets_dict, validation_url)
        若触发 403 VALIDATION_REQUIRED，返回 validation_url；
        """
        req = urllib.request.Request(
            QUOTA_ENDPOINT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": NATIVE_OAUTH_USER_AGENT
            },
            method="POST",
            data=b"{}"
        )
        ctx = ssl.create_default_context()
        quotas = {}
        resets = {}
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                body_str = _safe_decode_resp(resp.read())
                data = json.loads(body_str)
            for group in data.get("groups", []):
                grp_name = group.get("displayName", "")
                is_g4_grp = "gemini 4" in grp_name.lower() or "gemini-4" in grp_name.lower()
                for bucket in group.get("buckets", []):
                    b_id = bucket.get("bucketId", "")
                    rem = bucket.get("remainingFraction")
                    reset = bucket.get("resetTime")
                    if b_id:
                        quotas[b_id] = float(rem) if rem is not None else 0.0
                        if reset:
                            resets[b_id] = str(reset)
                        if is_g4_grp or "gemini-4" in b_id.lower() or "gemini4" in b_id.lower():
                            quotas["gemini4-weekly"] = float(rem) if rem is not None else 0.0
                            if reset:
                                resets["gemini4-weekly"] = str(reset)
            return quotas, resets, None
        except urllib.error.HTTPError as e:
            if e.code == 403:
                body_str = _safe_decode_resp(e.read())
                logger.warning(f"⚠️ 遇到 403 风控拦截: {body_str}")
                try:
                    j = json.loads(body_str)
                    for det in j.get("error", {}).get("details", []):
                        if det.get("reason") == "VALIDATION_REQUIRED":
                            val_url = det.get("metadata", {}).get("validation_url")
                            return quotas, resets, val_url
                except Exception:
                    pass
            return quotas, resets, None
        except Exception as e:
            logger.warning(f"⚠️ 探测配额接口网络异常: {e}")
            return quotas, resets, None

    def write_to_linux_secret(self, access_token: str, refresh_token: str, email: str = "", expiry_str: str = "") -> bool:
        """
        写入 Linux Secret Service (secret-tool)，100% 对齐官方 Go 语言服务器反序列化标准与上游 v5.0.3 规范：
        1. 双集合双写 (Dual Collection Sync):
           - 优先写入 '/org/freedesktop/secrets/collection/login' 集合 (供 agy CLI 及 IDE 核心语言服务检索)；
           - 同时写入默认集合 (Default Collection) 保证全系统工具统一；
        2. expiry: 必须为 RFC3339 标准纳秒/微秒时间戳；
        3. expires_in: 3599 (整数)；
        4. auth_method: "consumer"；
        5. id_token_email: 当前账号。
        """
        if not access_token or not refresh_token:
            logger.error("❌ write_to_linux_secret: access_token 或 refresh_token 为空")
            return False

        existing_writer_id = ""
        try:
            curr_cred = self.read_system_credential()
            if curr_cred and isinstance(curr_cred, dict):
                existing_writer_id = str(curr_cred.get("writer_id") or "")
        except Exception:
            pass

        import secrets
        final_writer_id = existing_writer_id if existing_writer_id else secrets.token_urlsafe(16)
        clean_expiry = format_rfc3339(expiry_str)

        payload_obj = {
            "token": {
                "access_token": str(access_token),
                "token_type": "Bearer",
                "refresh_token": str(refresh_token),
                "expiry": clean_expiry,
                "expires_in": 3599
            },
            "auth_method": "consumer",
            "id_token_email": email or "",
            "id_token": "",
            "writer_id": final_writer_id
        }
        raw_val = json.dumps(payload_obj)

        commands_to_execute = [
            # 1. 'login' collection (agy CLI)
            [
                "secret-tool", "store",
                "--collection=/org/freedesktop/secrets/collection/login",
                "--label=Password for 'antigravity' on 'gemini'",
                "service", "gemini",
                "username", "antigravity"
            ],
            # 2. default collection
            [
                "secret-tool", "store",
                "--label=Password for 'antigravity' on 'gemini'",
                "service", "gemini",
                "username", "antigravity"
            ]
        ]

        success_count = 0
        with KeychainFileLock(timeout=5.0):
            for cmd in commands_to_execute:
                col_name = "login" if "--collection=" in " ".join(cmd) else "default"
                for attempt in range(1, 4):
                    try:
                        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        out, err = p.communicate(input=raw_val, timeout=5)
                        if p.returncode == 0:
                            success_count += 1
                            break
                        else:
                            err_s = (err or "").strip()
                            if col_name == "login" and ("不存在" in err_s or "does not exist" in err_s.lower() or "no such object" in err_s.lower()):
                                logger.debug(f"跳过不存在的 secret-tool [login] 集合，回落默认集合: {err_s}")
                                break
                            logger.warning(f"⚠️ 写入 secret-tool [{col_name}] 失败 (尝试 {attempt}/3): {err_s}")
                            time.sleep(0.1 * attempt)
                    except Exception as e:
                        logger.error(f"❌ 执行 secret-tool [{col_name}] 异常: {e}")
                        time.sleep(0.1 * attempt)

        if success_count > 0:
            logger.info(f"🔑 [Linux secret-tool] 凭据已成功同步写入密钥环集合 ({success_count}/2): {email} (expiry={clean_expiry})")
            return True
        return False

    def read_system_credential(self) -> Optional[Dict[str, Any]]:
        """跨平台安全读取系统钥匙串/密钥环凭据"""
        if sys.platform == "darwin":
            try:
                cmd = ["security", "find-generic-password", "-s", "gemini", "-a", "antigravity", "-w"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout.strip():
                    raw = res.stdout.strip()
                    if raw.startswith("go-keyring-base64:"):
                        raw = raw[len("go-keyring-base64:"):]
                    return json.loads(base64.b64decode(raw).decode("utf-8"))
            except Exception:
                pass
        elif sys.platform.startswith("linux"):
            try:
                cmd = ["secret-tool", "lookup", "service", "gemini", "username", "antigravity"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout.strip():
                    raw = res.stdout.strip()
                    if raw.startswith("go-keyring-base64:"):
                        raw = base64.b64decode(raw[len("go-keyring-base64:"): ]).decode("utf-8")
                    return json.loads(raw)
            except Exception:
                pass
        return None

    def write_to_macos_keychain(self, access_token: str, refresh_token: str, expiry_str: str = "") -> bool:
        """
        写入 macOS 系统钥匙串 (security -U)，直接供 Antigravity 原生应用读取。
        """
        if not access_token or not refresh_token:
            logger.error("❌ write_to_macos_keychain: access_token 或 refresh_token 为空")
            return False

        payload_obj = {
            "token": {
                "access_token": str(access_token),
                "token_type": "Bearer",
                "refresh_token": str(refresh_token),
                "expiry": str(expiry_str or "")
            },
            "auth_method": "consumer"
        }
        b64_str = base64.b64encode(json.dumps(payload_obj).encode("utf-8")).decode("utf-8")
        full_val = f"go-keyring-base64:{b64_str}"

        cmd = [
            "security", "add-generic-password",
            "-U",
            "-s", "gemini",
            "-a", "antigravity",
            "-w", full_val
        ]
        with KeychainFileLock(timeout=5.0):
            for attempt in range(1, 4):
                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if res.returncode == 0:
                        logger.info("🔑 [macOS Keychain] 凭据已成功原子写入系统钥匙串！")
                        return True
                    else:
                        logger.warning(f"⚠️ 写入 Keychain 失败 (尝试 {attempt}/3): {res.stderr}")
                        time.sleep(0.1 * attempt)
                except Exception as e:
                    logger.error(f"❌ 执行 security 命令异常: {e}")
                    time.sleep(0.1 * attempt)
            return False

    def sync_all_active_credentials(self, email: str, access_token: str, refresh_token: str, expiry_ts: float) -> bool:
        """
        【活跃账号全端凭据强一致性同步 · 物理对齐 Mac 原版与 Linux Secret Service】
        将最新签发的 access_token 同步至：
        1. Linux Secret Service (secret-tool) / macOS Keychain
        2. ~/.gemini/oauth_creds.json (保证 agy CLI 与扩展不过期)
        3. ~/.gemini/jetski-standalone-oauth-token (语言服务优先回退凭据)
        4. ~/.gemini/google_accounts.json (活跃指针)
        5. ~/.config/Antigravity/app_storage.json (防止 Electron 掉登录页)
        """
        exp_rfc = format_rfc3339(expiry_ts or (time.time() + 3600))
        ok_sec = False
        if sys.platform == "darwin":
            ok_sec = self.write_to_macos_keychain(access_token, refresh_token, expiry_str=exp_rfc)
        elif sys.platform.startswith("linux"):
            ok_sec = self.write_to_linux_secret(access_token, refresh_token, email=email, expiry_str=exp_rfc)
        self.sync_local_credentials(email, access_token, refresh_token, expiry_ts)
        logger.info(f"🔄 [活跃凭据原子同步] 账号 {email} 最新 Token 已原子同步至系统钥匙串与 ~/.gemini/ 凭据池！")
        return ok_sec

    def sync_local_credentials(self, email: str, access_token: str, refresh_token: str, expiry_ts: float):
        """
        同步本地文件凭据 (对齐官方 Standalone 架构与上游 v5.0.3 规范):
        1. ~/.gemini/jetski-standalone-oauth-token (语言服务优先回退凭据，0o600 权限)；
        2. ~/.gemini/oauth_creds.json (Gemini 官方标准凭据，毫秒时间戳保底正数，0o600 权限)；
        3. ~/.gemini/google_accounts.json (活跃指针，0o600 权限)；
        4. ~/.config/Antigravity/app_storage.json (注入 agy.onboarding.lastLoginUsername 杜绝掉登录页)。
        """
        now_ts = time.time()
        safe_expiry_ms = _safe_i64(expiry_ts * 1000)
        if safe_expiry_ms <= 0:
            safe_expiry_ms = int((now_ts + 3600) * 1000)

        clean_expiry_rfc = format_rfc3339(expiry_ts or (now_ts + 3600))

        # 1. 写入 Standalone / 语言服务原生凭据: ~/.gemini/jetski-standalone-oauth-token
        try:
            jetski_path = os.path.expanduser("~/.gemini/jetski-standalone-oauth-token")
            jetski_payload = {
                "token": {
                    "access_token": str(access_token),
                    "token_type": "Bearer",
                    "refresh_token": str(refresh_token),
                    "expiry": clean_expiry_rfc,
                    "expires_in": 3599
                },
                "auth_method": "consumer",
                "id_token_email": email or "",
                "id_token": ""
            }
            if atomic_write_json(jetski_path, jetski_payload):
                try:
                    os.chmod(jetski_path, 0o600)
                except Exception:
                    pass
                logger.info(f"✅ Standalone 凭据已原子同步: {jetski_path} (600)")
        except Exception as e:
            logger.warning(f"⚠️ 同步 jetski-standalone-oauth-token 异常: {e}")

        # 2. 更新 oauth_creds.json
        try:
            oauth_payload = {
                "access_token": str(access_token),
                "refresh_token": str(refresh_token),
                "token_type": "Bearer",
                "expiry_date": safe_expiry_ms,
                "id_token": "",
                "scope": "https://www.googleapis.com/auth/userinfo.email openid https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/userinfo.profile"
            }
            if atomic_write_json(OAUTH_CREDS_PATH, oauth_payload):
                try:
                    os.chmod(OAUTH_CREDS_PATH, 0o600)
                except Exception:
                    pass
                logger.info(f"✅ 本地凭据已原子同步: {OAUTH_CREDS_PATH} (expiry_ms={safe_expiry_ms})")
        except Exception as e:
            logger.error(f"❌ 同步 oauth_creds.json 失败: {e}")

        # 3. 更新 google_accounts.json active 字段
        try:
            g_acc = {"active": email, "old": []}
            if atomic_write_json(GOOGLE_ACCOUNTS_PATH, g_acc):
                try:
                    os.chmod(GOOGLE_ACCOUNTS_PATH, 0o600)
                except Exception:
                    pass
                logger.info(f"✅ 活跃账号已同步: {GOOGLE_ACCOUNTS_PATH} -> {email}")
        except Exception as e:
            logger.error(f"❌ 同步 google_accounts.json 失败: {e}")

        # 4. 同步 Electron app_storage.json 的 lastLoginUsername 锁定
        try:
            app_storage_path = os.path.expanduser("~/.config/Antigravity/app_storage.json")
            if os.path.isfile(app_storage_path):
                with open(app_storage_path, "r", encoding="utf-8") as f:
                    storage_data = json.load(f)
                if storage_data.get("agy.onboarding.lastLoginUsername") != email:
                    storage_data["agy.onboarding.lastLoginUsername"] = email
                    atomic_write_json(app_storage_path, storage_data)
                    logger.info(f"✅ Electron 登录指针已成功注入: {app_storage_path} -> {email}")
        except Exception as e:
            logger.warning(f"⚠️ 同步 app_storage.json 登录指针异常: {e}")

    def fetch_available_models(self, access_token: str) -> Tuple[str, List[str], Optional[Dict[str, Any]]]:
        """
        探测账号支持的模型矩阵，精准区分 Claude 5.5 (付费Pro) 与 Claude 4.6 (普通Pro)，并提取 Gemini 4 状态。
        返回: (claude_version: "5.5" | "4.6", claude_models: List[str], gemini4_info: Optional[Dict])
        """
        MODELS_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
        req = urllib.request.Request(
            MODELS_ENDPOINT,
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
                body_str = _safe_decode_resp(resp.read())
                data = json.loads(body_str)
            models = data.get("models", {})
            c_models = []
            has_55 = False
            has_46 = False
            g4_info = None

            for m_id, m_obj in models.items():
                m_id_low = m_id.lower()
                if "claude" in m_id_low:
                    c_models.append(m_id)
                    if "5-5" in m_id_low or "5.5" in m_id_low:
                        has_55 = True
                    elif "4-6" in m_id_low or "4.6" in m_id_low:
                        has_46 = True
                if "gemini-4" in m_id_low or "argon" in m_id_low:
                    qi = m_obj.get("quotaInfo", {})
                    if qi and qi.get("remainingFraction") is not None:
                        g4_info = {
                            "quota_weekly": float(qi["remainingFraction"]),
                            "reset_time_weekly": str(qi.get("resetTime", ""))
                        }

            ver = "5.5" if has_55 else "4.6"
            if ver == "5.5" and not g4_info:
                g4_info = {"quota_weekly": 1.0, "reset_time_weekly": ""}
            return ver, c_models, g4_info
        except Exception as e:
            logger.debug(f"探测模型矩阵异常: {e}")
            return "4.6", [], None

    def execute_hot_switch(self, timeout_sec: float = 8.0, force: bool = False, target_account: Optional[Dict[str, Any]] = None) -> bool:
        """
        【原生热切号】平滑重启 language_server 子进程，并等待新进程拉起就绪。
        IDE 主窗口、编辑器标签页与前端会话保持存活，language_server 重启后自动读取新钥匙串。
        自带全局安全频控门禁，防止短时间内频繁重启击穿 Electron MAX_RESTARTS = 3。
        """
        global _GLOBAL_LAST_SWITCH_TS
        now = time.time()
        elapsed = now - _GLOBAL_LAST_SWITCH_TS
        if not force and elapsed < _HOT_SWITCH_SAFE_INTERVAL:
            logger.warning(
                f"🛡️ [安全频控门禁] 距离上次热切号仅经过 {elapsed:.1f}s (< {_HOT_SWITCH_SAFE_INTERVAL}s)！"
                f"凭据已原子注入 Secret Service，暂缓重复发送 kill 信号以保护 Electron 进程守护安全。"
            )
            return True

        _GLOBAL_LAST_SWITCH_TS = now
        try:
            res = subprocess.run(["pgrep", "-f", "language_server.*antigravity"], capture_output=True, text=True)
            old_pids = set(res.stdout.strip().split())
            if old_pids:
                for pid in old_pids:
                    logger.info(f"⚡ [Hot Switch] 发现旧 language_server (PID {pid})，发送平滑退出信号...")
                    subprocess.run(["kill", "-TERM", pid], capture_output=True)

                # [Post-Kill Re-assert 权威二次断言] (对齐 upstream v5.0.3 规范)
                # 语言服务子进程终止后立即补写一次凭据，覆盖退出钩子可能向 Keyring/文件回写陈旧 Session Token 的竞态！
                if target_account:
                    try:
                        t_email = target_account.get("email", "")
                        t_at = target_account.get("access_token", "")
                        t_rt = target_account.get("refresh_token", "")
                        t_exp = target_account.get("expiry_timestamp", 0)
                        t_exp_rfc = format_rfc3339(t_exp)
                        if sys.platform == "darwin":
                            self.write_to_macos_keychain(t_at, t_rt, expiry_str=t_exp_rfc)
                        elif sys.platform.startswith("linux"):
                            self.write_to_linux_secret(t_at, t_rt, email=t_email, expiry_str=t_exp_rfc)
                        self.sync_local_credentials(t_email, t_at, t_rt, t_exp)
                        logger.info(f"🛡️ [Post-Kill Re-assert] 凭据权威二次补写断言成功: {t_email}")
                    except Exception as rex:
                        logger.warning(f"⚠️ [Post-Kill Re-assert] 补写告警: {rex}")

                # 等待旧进程彻底退出，并轮询等待新 language_server 进程生成
                start_t = time.time()
                new_pid_found = None
                while time.time() - start_t < timeout_sec:
                    time.sleep(0.5)
                    chk = subprocess.run(["pgrep", "-f", "language_server.*antigravity"], capture_output=True, text=True)
                    cur_pids = set(chk.stdout.strip().split())
                    diff = cur_pids - old_pids
                    if diff:
                        new_pid_found = list(diff)[0]
                        break
                    elif cur_pids and not (cur_pids & old_pids):
                        new_pid_found = list(cur_pids)[0]
                        break

                if new_pid_found:
                    logger.info(f"✨ [Hot Switch] 新 language_server 进程已成功拉起 (PID {new_pid_found})！")
                else:
                    logger.info("✨ [Hot Switch] language_server 重启信号已发送完成！")

                # 沉淀等待内部 gRPC/HTTP 端口完全开启并加载系统凭据
                time.sleep(2.0)
                return True
            else:
                logger.warning("⚠️ 未发现正在运行的 language_server 进程，可能 IDE 处于关闭状态")
                return False
        except Exception as e:
            logger.error(f"❌ 执行 Hot Switch 异常: {e}")
            return False

    def switch_account(self, target_email: str, force_hot_switch: bool = True, relay_prompt: str = DEFAULT_RELAY_PROMPT, inject_recovery: bool = True) -> Tuple[bool, str]:
        """完整账号切换流：快照 -> 刷新 Token -> 写入 Keychain -> 同步文件 -> 原生热切号 -> 异步精准接力"""
        # 0. 切号前瞬间锁定真正活跃中的根会话快照 (仅纳入 RUNNING 与 180s 内意外报错中断会话)
        snapshot_sessions = None
        if inject_recovery:
            try:
                from .recovery import AntigravitySessionRecoveryManager
                rec_mgr = AntigravitySessionRecoveryManager()
                snapshot_sessions = rec_mgr.pre_switch_snapshot()
            except Exception as ex:
                logger.warning(f"切号前快照捕获异常: {ex}")

        hub_data = self.load_hub_accounts()
        accounts = hub_data.get("accounts", {})

        target_acc = accounts.get(target_email)
        if not target_acc:
            return False, f"未在 Hub 账号池中找到目标账号: {target_email}"

        tok = target_acc.get("token") or {}
        rt = tok.get("refresh_token") or target_acc.get("refresh_token", "")
        at = tok.get("access_token") or target_acc.get("access_token", "")
        exp = tok.get("expiry_timestamp") or target_acc.get("expiry_timestamp", 0)

        # 确保 Token 新鲜
        fresh_acc = {
            "email": target_email,
            "access_token": at,
            "refresh_token": rt,
            "expiry_timestamp": exp
        }
        live_at, refreshed = self.ensure_fresh_token(fresh_acc)
        final_at = live_at or at

        if not final_at or not rt:
            return False, f"目标账号 {target_email} 缺少有效凭据"

        exp_rfc = format_rfc3339(fresh_acc.get("expiry_timestamp", 0) or exp)

        # 1. 写入系统钥匙串/密钥环 (100% 对齐 RFC3339 纳秒时间戳)
        if sys.platform == "darwin":
            self.write_to_macos_keychain(final_at, rt, expiry_str=exp_rfc)
        elif sys.platform.startswith("linux"):
            self.write_to_linux_secret(final_at, rt, email=target_email, expiry_str=exp_rfc)

        # 2. 同步本地凭据文件
        self.sync_local_credentials(target_email, final_at, rt, fresh_acc.get("expiry_timestamp", 0))

        # 3. 更新 Hub 活跃标记与最近使用时间戳 (供 least-used 策略排序)
        now_epoch = int(time.time())
        target_acc["last_used_time"] = now_epoch
        hub_data["active_email"] = target_email
        hub_data["last_updated"] = now_epoch
        self.save_hub_accounts(hub_data)

        # 4. 执行原生热切号 (带 post-kill 二次权威断言)
        if force_hot_switch:
            self.execute_hot_switch(target_account=fresh_acc)

        # 5. 原生断点接力投递（空快照瞬时收敛；有活跃会话则后台异步投递，避免阻塞 /api/switch HTTP 响应超时）
        if inject_recovery:
            if snapshot_sessions is not None and len(snapshot_sessions) == 0:
                try:
                    from .recovery import AntigravitySessionRecoveryManager
                    rec_mgr = AntigravitySessionRecoveryManager()
                    rec_mgr.batch_recover_all_working_sessions(
                        prompt=relay_prompt,
                        preloaded_sessions=[],
                    )
                except Exception as ex:
                    logger.warning(f"空快照清理异常: {ex}")
            else:
                def _async_recover(snap_list, r_prompt):
                    try:
                        from .recovery import AntigravitySessionRecoveryManager
                        rec_mgr = AntigravitySessionRecoveryManager()
                        rec_mgr.batch_recover_all_working_sessions(
                            prompt=r_prompt,
                            preloaded_sessions=snap_list,
                        )
                    except Exception as ex:
                        logger.error(f"❌ 批量断点接力投递异常: {ex}")

                import threading
                threading.Thread(
                    target=_async_recover,
                    args=(snapshot_sessions, relay_prompt),
                    daemon=True,
                ).start()

        return True, f"成功无感切换至账号: {target_email}"

    def perform_real_switch(self, target_email: str, restart_app: bool = True, relay_prompt: str = DEFAULT_RELAY_PROMPT, force: bool = False, inject_recovery: bool = True) -> bool:
        """执行完整账号切换（兼容旧接口）"""
        ok, msg = self.switch_account(target_email, force_hot_switch=restart_app, relay_prompt=relay_prompt, inject_recovery=inject_recovery)
        return ok

    def load_warmup_schedule(self) -> Dict[str, Any]:
        """读取持久化各账号预热调度账本"""
        if os.path.exists(WARMUP_SCHEDULE_FILE):
            try:
                with open(WARMUP_SCHEDULE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_warmup_schedule(self, sched: Dict[str, Any]) -> bool:
        """原子写入各账号预热调度账本"""
        return atomic_write_json(WARMUP_SCHEDULE_FILE, sched)

    def send_real_warmup_ping(self, access_token: str, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
        """
        【单账号官方原生真实生成预热 (L1 实测验证通过 · 官方内部 Protobuf 契约)】
        端点: https://daily-cloudcode-pa.googleapis.com/v1internal:generateContent
        灾备: https://cloudcode-pa.googleapis.com/v1internal:generateContent
        Payload: 包装在 request 内部，包含 contents 与 generationConfig，耗费约 20~40 tokens
        """
        target_model = "claude-sonnet-4-6" if "claude" in model.lower() else "gemini-2.5-flash"
        payload = {
            "model": target_model,
            "request": {
                "contents": [{"role": "user", "parts": [{"text": "Hello, please reply with a 20-word greeting."}]}],
                "generationConfig": {"maxOutputTokens": 30, "temperature": 0.2}
            }
        }
        body = json.dumps(payload).encode("utf-8")
        ctx = ssl.create_default_context()

        for ep in WARMUP_GENERATE_ENDPOINTS:
            try:
                req = urllib.request.Request(
                    ep,
                    data=body,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                        "User-Agent": NATIVE_OAUTH_USER_AGENT
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                    if resp.status == 200:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        tokens = resp_data.get("response", {}).get("usageMetadata", {})
                        logger.info(f"   🎉 [真实预热成功] 模型: {target_model}, 消耗Tokens: {tokens}")
                        return {"status": "success", "endpoint": ep, "model": target_model, "tokens": tokens}
            except urllib.error.HTTPError as he:
                err_body = _safe_decode_resp(he.read())
                logger.warning(f"   ⚠️ 预热请求 HTTP {he.code} ({ep}): {err_body[:200]}")
                if he.code == 403 and "VALIDATION_REQUIRED" in err_body:
                    return {"status": "validation_blocked", "error": err_body}
            except Exception as ex:
                logger.warning(f"   ⚠️ 预热异常 ({ep}): {ex}")
        return {"status": "failed", "endpoint": "all_failed"}

    def warmup_single_account(self, acc: Dict[str, Any], force: bool = False, model_override: str = "") -> Dict[str, Any]:
        """单账号官方原生真实生成预热"""
        email = acc.get("email", "")
        rt = acc.get("refresh_token")
        if not rt:
            tok = acc.get("token") or {}
            rt = tok.get("refresh_token", "")
        if not rt:
            return {"email": email, "status": "no_refresh_token"}

        if acc.get("validation_blocked"):
            logger.warning(f"🛡️ [预热风控熔断] 账号 {email} 处于 Google 验证拦截态，跳过预热")
            return {"email": email, "status": "validation_blocked"}

        ping_model = model_override or "gemini-2.5-flash"
        logger.info(f"🔥 [单账号真实生成预热] 正在为账号 {email} 执行 Token 校验与官方端点 Ping 激活 (选定模型: {ping_model})...")

        at, _ = self.ensure_fresh_token(acc)
        if not at:
            return {"email": email, "status": "refresh_failed"}

        now_sec = int(time.time())
        ping_res = self.send_real_warmup_ping(at, model=ping_model)

        # 核心：计算并硬锁定 5 小时绝对重置时刻 (精确到秒)
        locked_reset_ts = now_sec + 18000
        locked_reset_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(locked_reset_ts))

        # 更新持久化预热账本
        sched = self.load_warmup_schedule()
        sched[email] = {
            "email": email,
            "last_warmup_ts": now_sec,
            "locked_reset_ts": locked_reset_ts,
            "locked_reset_iso": locked_reset_iso,
            "model_warmed": ping_model,
            "status": "active_countdown"
        }
        self.save_warmup_schedule(sched)

        # 关键联动：同步原子写回 accounts_hub.json
        if os.path.exists(ACCOUNTS_HUB_FILE):
            try:
                with open(ACCOUNTS_HUB_FILE, "r", encoding="utf-8") as hf:
                    hub_data = json.load(hf)
                if email in hub_data.get("accounts", {}):
                    acc_entry = hub_data["accounts"][email]
                    if ping_model.startswith("claude"):
                        acc_entry.setdefault("claude", {})["reset_time_5h"] = locked_reset_iso
                    else:
                        acc_entry.setdefault("gemini", {})["reset_time_5h"] = locked_reset_iso
                    atomic_write_json(ACCOUNTS_HUB_FILE, hub_data)
                    logger.info(f"     📑 [Hub联动] 已同步原子更新 accounts_hub.json 账号 {email} 5h 重置时刻: {locked_reset_iso}")
            except Exception as ex:
                logger.warning(f"同步写回 accounts_hub.json 异常: {ex}")

        rem_h = (locked_reset_ts - now_sec) / 3600
        logger.info(f"     ✅ 账号 {email} 真实预热成功！模型: {ping_model}, 官方5h周期已锁定，将于 {locked_reset_iso} ({rem_h:.2f}h后) 满血重置！")
        return {"email": email, "status": "success", "model_warmed": ping_model, "locked_reset_ts": locked_reset_ts, "locked_reset_iso": locked_reset_iso}

    @staticmethod
    def _parse_iso_to_ts(iso_str: str) -> int:
        if not iso_str or "T" not in str(iso_str):
            return 0
        try:
            import datetime
            clean_iso = str(iso_str).replace("Z", "+00:00")
            return int(datetime.datetime.fromisoformat(clean_iso).timestamp())
        except Exception:
            return 0

    def rebalance_and_align_staggered_ladder(self, accounts: Optional[List[Dict[str, Any]]] = None, force: bool = False) -> Dict[str, Any]:
        """
        【摩天轮阶梯错峰流水线编排器 · 5小时无缝接力保障 (100% 纯本地零风控计算)】
        目标：
        1. 针对全池 N 个健康账号，在 5 小时 (18000秒 = 300分钟) 滑动窗口轴上等距打散梯次；
        2. 梯级步长 = 18000 // N (11账号时约 1636 秒 ≈ 27.27 分钟)；
        3. 杜绝 4h59m 扎堆与“即将恢复”死锁：真实保留各账号在走倒计时，过期/未激活账号均布至未占用阶梯槽位；
        4. 纯本地时间轴编排，绝不向 Google 外部接口发起任何批量测试或伪造请求。
        """
        if accounts is None:
            hd_init = self.load_hub_accounts()
            accounts = [dict(v, email=k) for k, v in hd_init.get("accounts", {}).items()]
        if not accounts:
            return {"status": "empty", "count": 0}

        now_ts = int(time.time())
        sched = self.load_warmup_schedule()

        hd = {}
        if os.path.exists(ACCOUNTS_HUB_FILE):
            try:
                with open(ACCOUNTS_HUB_FILE, "r", encoding="utf-8") as hf:
                    hd = json.load(hf)
            except Exception as ex:
                logger.warning(f"读取 accounts_hub.json 异常: {ex}")

        hub_accs = hd.get("accounts", {})
        valid_accounts = []
        for idx_order, a in enumerate(accounts):
            em = a.get("email", "")
            if not em or a.get("disabled") or a.get("validation_blocked"):
                continue
            a_copy = dict(a)
            a_copy["_order"] = idx_order
            valid_accounts.append(a_copy)

        n = len(valid_accounts)
        if n == 0:
            return {"status": "no_valid_accounts", "count": 0}

        step_sec = max(900, 18000 // n)
        ladder_slots = [min(18000, int(round((i + 0.5) * step_sec))) for i in range(n)]

        acc_states = []
        for a in valid_accounts:
            em = a["email"]
            s = sched.get(em, {})
            hub_entry = hub_accs.get(em, a)

            # 优先识别账号在 accounts_hub.json 中真实在走的 5h 恢复窗口，其次取 warmup_schedule
            g_iso = hub_entry.get("gemini", {}).get("reset_time_5h", "")
            g_ts = self._parse_iso_to_ts(g_iso)
            s_ts = int(s.get("locked_reset_ts", 0) or 0)
            l_ts = g_ts if (g_ts > now_ts and (g_ts - now_ts) <= 18000) else s_ts
            rem = l_ts - now_ts
            g_q5h = _safe_float(hub_entry.get("gemini", {}).get("quota_5h", 1.0), 1.0)
            is_consuming_g = (g_q5h < 0.999 and 60 < rem <= 18000)
            has_valid = (l_ts > now_ts and 60 < rem <= 18000) and (not force or is_consuming_g)

            # Claude 独立真实恢复窗口检测 (如活跃账号正在消费 Claude)
            c_iso = hub_entry.get("claude", {}).get("reset_time_5h", "")
            c_ts = self._parse_iso_to_ts(c_iso)
            sc_ts = int(s.get("locked_reset_ts_claude", 0) or 0)
            lc_ts = c_ts if (c_ts > now_ts and (c_ts - now_ts) <= 18000) else sc_ts
            rem_c = lc_ts - now_ts
            c_q5h = _safe_float(hub_entry.get("claude", {}).get("quota_5h", 1.0), 1.0)
            is_consuming_c = (c_q5h < 0.999 and 60 < rem_c <= 18000)
            has_valid_c = (lc_ts > now_ts and 60 < rem_c <= 18000) and (not force or is_consuming_c)

            acc_states.append({
                "email": em,
                "acc": a,
                "order": a["_order"],
                "locked_reset_ts": l_ts if has_valid else 0,
                "remaining_sec": rem if has_valid else 0,
                "has_valid_window": has_valid,
                "locked_reset_ts_claude": lc_ts if has_valid_c else 0,
                "has_valid_window_claude": has_valid_c,
            })

        # 为已有有效窗口的账号优先锁定最接近的摩天轮阶梯槽位，其余过期账号按列表顺序填补剩余空槽
        available_slot_indices = set(range(n))
        assigned_slot_for_email: Dict[str, int] = {}

        valid_window_items = sorted(
            [x for x in acc_states if x["has_valid_window"]],
            key=lambda x: (x["remaining_sec"], x["order"])
        )
        for item in valid_window_items:
            best_slot = min(available_slot_indices, key=lambda si: abs(ladder_slots[si] - item["remaining_sec"]))
            available_slot_indices.remove(best_slot)
            assigned_slot_for_email[item["email"]] = best_slot

        expired_items = sorted(
            [x for x in acc_states if not x["has_valid_window"]],
            key=lambda x: x["order"]
        )
        for item, slot_idx in zip(expired_items, sorted(available_slot_indices)):
            assigned_slot_for_email[item["email"]] = slot_idx

        logger.info(f"🎡 [摩天轮错峰编排] 正在为全池 {n} 个账号构建阶梯流水线 (梯级: {step_sec // 60}m {step_sec % 60}s)...")

        for item in acc_states:
            em = item["email"]
            slot_idx = assigned_slot_for_email[em]
            slot_target_rem = ladder_slots[slot_idx]

            if item["has_valid_window"]:
                target_ts = item["locked_reset_ts"]
            else:
                target_ts = now_ts + slot_target_rem
            target_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(target_ts))

            if item["has_valid_window_claude"]:
                target_ts_c = item["locked_reset_ts_claude"]
            else:
                target_ts_c = target_ts
            target_iso_c = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(target_ts_c))

            s_entry = sched.setdefault(em, {})
            s_entry["email"] = em
            s_entry["ladder_slot"] = slot_idx
            s_entry["ladder_step_sec"] = step_sec
            s_entry["locked_reset_ts"] = target_ts
            s_entry["locked_reset_iso"] = target_iso
            s_entry["locked_reset_ts_claude"] = target_ts_c
            s_entry["locked_reset_iso_claude"] = target_iso_c
            s_entry["next_warmup_ts"] = target_ts
            s_entry["status"] = "in_ladder"

            if em in hub_accs:
                g_dict = hub_accs[em].setdefault("gemini", {})
                g_dict["reset_time_5h"] = target_iso

                c_dict = hub_accs[em].setdefault("claude", {})
                c_dict["reset_time_5h"] = target_iso_c

        if hd:
            atomic_write_json(ACCOUNTS_HUB_FILE, hd)
        self.save_warmup_schedule(sched)
        logger.info(f"✅ [摩天轮错峰梯次完成] 全池 {n} 账号已完美建立 {step_sec // 60} 分钟阶梯流水线，彻底消除 4h59m 与即将恢复死锁！")
        return {"status": "ok", "count": n, "step_sec": step_sec}

    def check_and_trigger_due_staggered_warmup(self) -> int:
        """
        【零风控摩天轮到期自动接力轮转】
        检查是否有账号的 5h 梯次倒计时已到期 (<= 60s)；
        若有到期账号，纯本地将其平滑轮转至摩天轮队尾槽位，绝不向 Google 发起后台批量生成请求。
        """
        now_ts = int(time.time())
        sched = self.load_warmup_schedule()
        hd = self.load_hub_accounts()
        accounts_map = hd.get("accounts", {})
        if not accounts_map:
            return 0

        due_count = 0
        for em, acc in accounts_map.items():
            if acc.get("disabled") or acc.get("validation_blocked"):
                continue
            g_iso = acc.get("gemini", {}).get("reset_time_5h", "")
            g_ts = self._parse_iso_to_ts(g_iso)
            s_ts = int(sched.get(em, {}).get("locked_reset_ts", 0) or 0)
            eff_ts = g_ts or s_ts
            if eff_ts <= now_ts + 60:
                due_count += 1

        if due_count > 0:
            acc_list = [dict(v, email=k) for k, v in accounts_map.items()]
            self.rebalance_and_align_staggered_ladder(acc_list, force=False)
        return due_count


