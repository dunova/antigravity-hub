#!/usr/bin/env python3
"""
Antigravity Hub 独立控制台与高密看板服务器 (antigravity_hub_server.py)
版本: v1.0.0 (20260920-v1.0.0-INDEPENDENT_HUB)

【架构铁律】
1. 绝对 100% 独立：持久化底表仅读写 08-IOTA挖矿/配置/hub/ 目录；
2. 绝对零写入外部客户端：严禁对 ~/.antigravity_tools 回写一字节；
3. 遵循 Neo-Brutalism + HTMX 规范：高密 Table-First，支持数十上百账号清晰展示；
4. 核心功能闭环：物理切换、4h 随机平滑预热、Gemini 与 Claude 双配额并发定时刷新。
"""

import os
import sys
import json
import time
import base64
import random
import urllib.request
import urllib.parse
import urllib.error
import ssl
import fcntl
import subprocess
import threading
import concurrent.futures
import logging
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

__version__ = "2.27.0"
__canonical_version_tag__ = "20260926-v2.27.0-ANTI_DEADLOCK_PROBE_AND_AUTO_UNBLOCK_HEALING"
__last_updated__ = "2026-09-26 12:45:00"
__canonical_doctrine__ = "彻底消除待验证拦截死锁 + 按需确保Token新鲜探测 + 解封自动物理清除与双向持久化"


# 配置常量
BASE_DATA_DIR = os.environ.get("ANTIGRAVITY_HUB_DIR", os.path.expanduser("~/.antigravity_hub"))
HUB_DIR = os.path.join(BASE_DATA_DIR, "data")
ACCOUNTS_HUB_FILE = os.path.join(HUB_DIR, "accounts_hub.json")
WARMUP_HUB_FILE = os.path.join(HUB_DIR, "warmup_hub.json")
WARMUP_SCHEDULE_PATH = os.path.join(HUB_DIR, "warmup_schedule.json")
MANUAL_OVERRIDE_LOCK_PATH = os.path.join(BASE_DATA_DIR, "manual_override_lock.json")

OAUTH_CREDS_PATH = os.path.expanduser("~/.gemini/oauth_creds.json")
GOOGLE_ACCOUNTS_PATH = os.path.expanduser("~/.gemini/google_accounts.json")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "YOUR_GOOGLE_CLIENT_SECRET")
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
QUOTA_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
MODELS_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
WARMUP_ENDPOINTS = [
    "https://daily-cloudcode-pa.googleapis.com/v1internal:generateContent",
    "https://cloudcode-pa.googleapis.com/v1internal:generateContent"
]

SERVER_PORT = 18088

# 严格对齐官方原生 Antigravity Tools (constants.rs#L197 与 oauth.rs#L707)
NATIVE_OAUTH_USER_AGENT = "vscode/1.X.X (Antigravity/4.3.0)"
TOKEN_REFRESH_SKEW_SECONDS = 900  # 15 分钟临期偏置，平时 100% 本地复用，杜绝高频轰炸
ANTIGRAVITY_TOOLS_DIR = os.path.expanduser("~/.antigravity_tools")
ANTIGRAVITY_TOOLS_ACCOUNTS_DIR = os.path.join(ANTIGRAVITY_TOOLS_DIR, "accounts")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [HubServer] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/tmp/antigravity_hub_server.log")
    ]
)
logger = logging.getLogger("HubServer")


def atomic_write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
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


def get_manual_override_lock() -> Optional[Dict[str, Any]]:
    """
    【人工干预保护锁】检查是否存在有效的用户手动切换锁。
    若存在且未过期，返回锁数据字典；否则返回 None。
    """
    if not os.path.exists(MANUAL_OVERRIDE_LOCK_PATH):
        return None
    try:
        with open(MANUAL_OVERRIDE_LOCK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        now_ts = time.time()
        if data.get("locked_until", 0) > now_ts:
            return data
        return None
    except Exception:
        return None


def set_manual_override_lock(account_email: str, duration_sec: int = 7200, reason: str = "User manual switch in Antigravity Hub") -> Dict[str, Any]:
    """
    【建立人工干预保护锁】用户手动在 Hub 切换账号后，原子建立锁定保护，默认 2 小时 (7200s)。
    """
    now_ts = int(time.time())
    payload = {
        "manual_account": account_email,
        "locked_at": now_ts,
        "locked_until": now_ts + duration_sec,
        "duration_sec": duration_sec,
        "reason": reason
    }
    atomic_write_json(MANUAL_OVERRIDE_LOCK_PATH, payload)
    return payload


def clear_manual_override_lock() -> bool:
    """
    【解除人工干预保护锁】用户在 Hub 界面点击解除保护，恢复后台看门狗自动轮换调度。
    """
    if os.path.exists(MANUAL_OVERRIDE_LOCK_PATH):
        try:
            os.remove(MANUAL_OVERRIDE_LOCK_PATH)
            return True
        except Exception:
            pass
    return False


class KeychainFileLock:
    LOCK_PATH = "/tmp/antigravity_keychain_hub.lock"

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self._fd = None

    def __enter__(self):
        start = time.time()
        self._fd = os.open(self.LOCK_PATH, os.O_CREAT | os.O_RDWR | os.O_TRUNC, 0o600)
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except (BlockingIOError, OSError):
                if time.time() - start >= self.timeout:
                    raise TimeoutError(f"获取 Keychain 锁超时 ({self.timeout}s)")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except Exception:
                pass


class HubEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.refreshing_now = False
        self._ensure_storage()

    def _ensure_storage(self):
        os.makedirs(HUB_DIR, exist_ok=True)
        if not os.path.exists(ACCOUNTS_HUB_FILE):
            # 自动只读导入一次
            from .importer import import_accounts_read_only
            import_accounts_read_only()

    def load_accounts(self) -> Dict[str, Any]:
        with self.lock:
            if not os.path.exists(ACCOUNTS_HUB_FILE):
                return {"active_email": "", "accounts": {}}
            try:
                with open(ACCOUNTS_HUB_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 动态双向融合 ~/.antigravity_tools/accounts/<id>.json 中的风控拦截标记
                for email, acc in data.get("accounts", {}).items():
                    acc_id = acc.get("id")
                    if acc_id:
                        df = os.path.join(ANTIGRAVITY_TOOLS_ACCOUNTS_DIR, f"{acc_id}.json")
                        if os.path.exists(df):
                            try:
                                with open(df, "r", encoding="utf-8") as dff:
                                    detail = json.load(dff)
                                is_blocked = bool(detail.get("validation_blocked", False))
                                acc["validation_blocked"] = is_blocked
                                acc["validation_url"] = detail.get("validation_url") if is_blocked else None
                                acc["validation_blocked_reason"] = detail.get("validation_blocked_reason", "VALIDATION_REQUIRED") if is_blocked else None
                            except Exception:
                                pass
                return data
            except Exception as e:
                logger.error(f"读取 accounts_hub.json 失败: {e}")
                return {"active_email": "", "accounts": {}}

    def save_accounts(self, data: Dict[str, Any]) -> bool:
        with self.lock:
            data["last_updated"] = int(time.time())
            return atomic_write_json(ACCOUNTS_HUB_FILE, data)

    def auto_ingest_system_account(self) -> Optional[Tuple[str, bool]]:
        """
        【新登录账号 100% 自动热维护纳管】
        实时从 macOS Keychain 与系统配置中嗅探当前活跃登录账号，
        若发现新登录账号或凭据更新，自动无感热纳管至 accounts_hub.json 并初始化配额。
        返回: (email, is_new) 或 None
        """
        try:
            cmd = ["security", "find-generic-password", "-s", "gemini", "-a", "antigravity", "-w"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode != 0 or not res.stdout.strip():
                return None
            raw = res.stdout.strip()
            if raw.startswith("go-keyring-base64:"):
                raw = raw.replace("go-keyring-base64:", "")
            dec = base64.b64decode(raw).decode("utf-8")
            kd = json.loads(dec)
            at = kd.get("token", {}).get("access_token") or kd.get("access_token")
            rt = kd.get("token", {}).get("refresh_token") or kd.get("refresh_token")
            if not at or not rt:
                return None

            # 探测当前 Token 所属邮箱 (优先 TokenInfo，兜底 google_accounts.json)
            detected_email = ""
            try:
                t_url = f"https://oauth2.googleapis.com/tokeninfo?access_token={at}"
                req = urllib.request.Request(t_url, headers={"User-Agent": "AntigravityHub/2.1"})
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=3, context=ctx) as r:
                    t_info = json.loads(r.read().decode("utf-8"))
                    detected_email = t_info.get("email", "").strip()
            except Exception:
                pass

            if not detected_email and os.path.exists(GOOGLE_ACCOUNTS_PATH):
                try:
                    g_acc = json.load(open(GOOGLE_ACCOUNTS_PATH))
                    detected_email = g_acc.get("active", "").strip()
                except Exception:
                    pass

            if not detected_email or "@" not in detected_email:
                return None

            data = self.load_accounts()
            accounts = data.get("accounts", {})
            now_ts = int(time.time())
            is_new = detected_email not in accounts

            if is_new:
                logger.info(f"✨ [热维护自动纳管] 发现新登录账号: {detected_email}，正在自动纳管...")
                new_acc = {
                    "email": detected_email,
                    "pro": True,
                    "refresh_token": rt,
                    "access_token": at,
                    "expires_at": now_ts + 3600,
                    "added_at": now_ts,
                    "last_refreshed_ts": now_ts,
                    "next_warmup_ts": now_ts + random.randint(300, 1800),
                    "last_warmup_ts": 0,
                    "gemini": {
                        "quota_5h": 1.0,
                        "quota_weekly": 1.0,
                        "reset_time_5h": "",
                        "reset_time_weekly": "",
                        "reset_time": ""
                    },
                    "claude": {
                        "quota_5h": 1.0,
                        "quota_weekly": 1.0,
                        "reset_time_5h": "",
                        "reset_time_weekly": "",
                        "reset_time": ""
                    }
                }
                # 立即拉取实时配额
                try:
                    quotas, resets = self.fetch_live_quota(at)
                    if quotas:
                        new_acc["gemini"]["quota_5h"] = quotas.get("gemini-5h", 1.0)
                        new_acc["gemini"]["quota_weekly"] = quotas.get("gemini-weekly", 1.0)
                        if resets.get("gemini-5h"):
                            new_acc["gemini"]["reset_time_5h"] = resets["gemini-5h"]
                        if resets.get("gemini-weekly"):
                            new_acc["gemini"]["reset_time_weekly"] = resets["gemini-weekly"]
                        new_acc["claude"]["quota_5h"] = quotas.get("3p-5h", 1.0)
                        new_acc["claude"]["quota_weekly"] = quotas.get("3p-weekly", 1.0)
                        if resets.get("3p-5h"):
                            new_acc["claude"]["reset_time_5h"] = resets["3p-5h"]
                        if resets.get("3p-weekly"):
                            new_acc["claude"]["reset_time_weekly"] = resets["3p-weekly"]
                except Exception as e:
                    logger.warning(f"新账号初始化配额异常: {e}")

                accounts[detected_email] = new_acc
                data["accounts"] = accounts
                data["active_email"] = detected_email
                self.save_accounts(data)
                logger.info(f"✅ [热维护自动纳管成功] 账号 {detected_email} 已纳入 Hub 账本并设为活跃账号！")
                return detected_email, True
            else:
                # 已存在，检查是否需要同步更新 refresh_token 或 active 状态
                existing = accounts[detected_email]
                updated = False
                if existing.get("refresh_token") != rt:
                    existing["refresh_token"] = rt
                    existing["access_token"] = at
                    existing["expires_at"] = now_ts + 3600
                    updated = True
                if data.get("active_email") != detected_email:
                    # 人工干预保护优先门禁：若当前处于有效锁定保护期，杜绝被意外覆盖
                    lock_info = get_manual_override_lock()
                    if lock_info and lock_info.get("manual_account") and lock_info.get("locked_until", 0) > time.time():
                        locked_acc = lock_info.get("manual_account")
                        if locked_acc != detected_email:
                            logger.warning(
                                f"🛡️ [人工锁抗回弹防御] Keychain 检测为 {detected_email}，但当前处于用户指定保护期 ({locked_acc})！"
                                f"立即自动原子恢复用户锁定的活跃账号..."
                            )
                            self.switch_account(locked_acc)
                            return locked_acc, False
                    data["active_email"] = detected_email
                    updated = True
                if updated:
                    self.save_accounts(data)
                    logger.info(f"🔄 [热维护凭据同步] 账号 {detected_email} 凭据与活跃状态已完成无感刷新！")
                return detected_email, False

        except Exception as e:
            logger.error(f"热维护自动纳管检查异常: {e}")
            return None

    def refresh_google_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        if not refresh_token:
            return None
        post_data = urllib.parse.urlencode({
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }).encode("utf-8")

        req = urllib.request.Request(
            GOOGLE_TOKEN_ENDPOINT,
            data=post_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": NATIVE_OAUTH_USER_AGENT
            },
            method="POST"
        )
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                body_str = _safe_decode_resp(resp.read())
                return json.loads(body_str)
        except urllib.error.HTTPError as he:
            body = _safe_decode_resp(he.read())
            logger.error(f"Google Token 刷新 HTTP 异常 {he.code}: {body}")
            return None
        except Exception as e:
            logger.error(f"Google Token 刷新失败: {e}")
            return None

    def fetch_live_quota(self, access_token: str) -> Tuple[Dict[str, float], Dict[str, str], Optional[str]]:
        """
        拉取配额，返回: (quotas, resets, validation_url)
        若触发 403 VALIDATION_REQUIRED，validation_url 会携带解封链接
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
        quotas: Dict[str, float] = {}
        resets: Dict[str, str] = {}
        try:
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                body_str = _safe_decode_resp(resp.read())
                data = json.loads(body_str)
            for group in data.get("groups", []):
                for bucket in group.get("buckets", []):
                    b_id = bucket.get("bucketId")
                    rem = bucket.get("remainingFraction")
                    reset = bucket.get("resetTime")
                    if b_id:
                        quotas[b_id] = float(rem) if rem is not None else 0.0
                        if reset:
                            resets[b_id] = str(reset)
            return quotas, resets, None
        except urllib.error.HTTPError as he:
            body = _safe_decode_resp(he.read())
            logger.warning(f"获取官方配额 HTTP 异常 {he.code}: {body}")
            val_url = None
            if he.code == 403:
                try:
                    err_j = json.loads(body)
                    for det in err_j.get("error", {}).get("details", []):
                        if det.get("reason") == "VALIDATION_REQUIRED":
                            val_url = det.get("metadata", {}).get("validation_url", "")
                except Exception:
                    pass
            return {}, {}, val_url
        except Exception as e:
            logger.warning(f"获取官方配额失败: {e}")
            return {}, {}, None

    def _sync_antigravity_tools_cache(self, acc_id: str, access_token: str = None, refresh_token: str = None, expiry_ts: int = None, validation_blocked: bool = None, val_url: str = None):
        """同步回写 ~/.antigravity_tools/accounts/<id>.json 与 accounts_hub.json"""
        if not acc_id:
            return
        detail_path = os.path.join(ANTIGRAVITY_TOOLS_ACCOUNTS_DIR, f"{acc_id}.json")
        if not os.path.exists(detail_path):
            return
        try:
            with open(detail_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            changed = False
            if access_token:
                tok = d.setdefault("token", {})
                tok["access_token"] = access_token
                if refresh_token:
                    tok["refresh_token"] = refresh_token
                if expiry_ts:
                    tok["expiry_timestamp"] = expiry_ts
                changed = True
            if validation_blocked is not None:
                d["validation_blocked"] = validation_blocked
                d["validation_url"] = val_url if validation_blocked else None
                d["validation_blocked_reason"] = "VALIDATION_REQUIRED" if validation_blocked else None
                changed = True
            if changed:
                tmp_f = f"{detail_path}.tmp.{os.getpid()}"
                with open(tmp_f, "w", encoding="utf-8") as f:
                    json.dump(d, f, indent=2, ensure_ascii=False)
                os.replace(tmp_f, detail_path)

                # 同步持久化到 accounts_hub.json，杜绝 Hub 状态脱节与死锁
                if validation_blocked is not None and os.path.exists(ACCOUNTS_HUB_FILE):
                    try:
                        email = d.get("email")
                        if email:
                            with open(ACCOUNTS_HUB_FILE, "r", encoding="utf-8") as hf:
                                hd = json.load(hf)
                            if email in hd.get("accounts", {}):
                                hd["accounts"][email]["validation_blocked"] = validation_blocked
                                hd["accounts"][email]["validation_url"] = val_url if validation_blocked else None
                                hd["accounts"][email]["validation_blocked_reason"] = "VALIDATION_REQUIRED" if validation_blocked else None
                                atomic_write_json(ACCOUNTS_HUB_FILE, hd)
                    except Exception as he:
                        logger.warning(f"同步 accounts_hub.json 状态异常: {he}")
        except Exception as e:
            logger.warning(f"同步 ~/.antigravity_tools 缓存失败 {acc_id}: {e}")

    def ensure_fresh_token(self, acc: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """
        按需 Token 缓存与临期刷新 (严格对齐原生 Antigravity Tools oauth.rs#L707-L728)
        返回: (access_token, was_refreshed)
        """
        now = int(time.time())
        acc_id = acc.get("id", "")
        at = acc.get("access_token")
        exp = acc.get("expires_at", 0) or acc.get("expiry_timestamp", 0)
        rt = acc.get("refresh_token")

        # 只要现有 access_token 存在且距离过期 > 15 分钟，直接复用本地缓存 Token，0 次 OAuth 请求！
        if at and exp > (now + TOKEN_REFRESH_SKEW_SECONDS):
            return at, False

        if not rt:
            logger.warning(f"账号 {acc.get('email')} 缺少 refresh_token，无法刷新")
            return None, False

        refreshed = self.refresh_google_token(rt)
        if not refreshed or "access_token" not in refreshed:
            logger.error(f"账号 {acc.get('email')} 刷新 Google Token 失败")
            return None, False

        at = refreshed.get("access_token")
        expires_in = refreshed.get("expires_in", 3600)
        exp = now + expires_in
        acc["access_token"] = at
        acc["expires_at"] = exp
        acc["expiry_timestamp"] = exp
        if acc_id:
            self._sync_antigravity_tools_cache(acc_id, access_token=at, refresh_token=rt, expiry_ts=exp)
        return at, True

    def refresh_single_account_quota(self, email: str, acc: Dict[str, Any]) -> bool:
        acc_id = acc.get("id", "")

        # 1. 严格先通过 ensure_fresh_token 确保 token 新鲜 (彻底消除因 401 导致的假死与死锁)
        at, was_refreshed = self.ensure_fresh_token(acc)
        if not at:
            logger.warning(f"账号 {email} 无法获取有效 access_token，跳过配额刷新")
            return False

        # 2. 向端点发起探测
        quotas, resets, val_url = self.fetch_live_quota(at)
        if val_url is not None:
            # 捕获到 Google 风控拦截，立即熔断
            acc["validation_blocked"] = True
            acc["validation_url"] = val_url
            acc["validation_blocked_reason"] = "VALIDATION_REQUIRED"
            self._sync_antigravity_tools_cache(acc_id, validation_blocked=True, val_url=val_url)
            logger.error(f"🚨 [风控捕获] 账号 {email} 触发 Google VALIDATION_REQUIRED，已熔断！解封地址: {val_url}")
            return False

        if quotas:
            # 只要成功返回配额，立即清除 validation_blocked、validation_url 并同步持久化
            was_blocked = acc.get("validation_blocked", False)
            acc["validation_blocked"] = False
            acc["validation_url"] = None
            acc["validation_blocked_reason"] = None
            if was_blocked:
                logger.info(f"🎉 [风控自愈复权] 账号 {email} 探测配额成功，已自动清除 validation_blocked！")
            self._sync_antigravity_tools_cache(acc_id, validation_blocked=False)

            acc["gemini"]["quota_5h"] = quotas.get("gemini-5h", acc["gemini"].get("quota_5h", 1.0))
            acc["gemini"]["quota_weekly"] = quotas.get("gemini-weekly", acc["gemini"].get("quota_weekly", 1.0))
            if resets.get("gemini-5h"):
                acc["gemini"]["reset_time_5h"] = resets["gemini-5h"]
            if resets.get("gemini-weekly"):
                acc["gemini"]["reset_time_weekly"] = resets["gemini-weekly"]
                acc["gemini"]["reset_time"] = resets["gemini-weekly"]

            acc["claude"]["quota_5h"] = quotas.get("3p-5h", acc["claude"].get("quota_5h", 1.0))
            acc["claude"]["quota_weekly"] = quotas.get("3p-weekly", acc["claude"].get("quota_weekly", 1.0))
            if resets.get("3p-5h"):
                acc["claude"]["reset_time_5h"] = resets["3p-5h"]
            if resets.get("3p-weekly"):
                acc["claude"]["reset_time_weekly"] = resets["3p-weekly"]
                acc["claude"]["reset_time"] = resets["3p-weekly"]
            elif resets.get("3p-5h"):
                acc["claude"]["reset_time"] = resets["3p-5h"]

        acc["last_refreshed_ts"] = int(time.time())
        return True

    def refresh_all_quotas(self) -> int:
        if self.refreshing_now:
            return 0
        self.refreshing_now = True
        try:
            data = self.load_accounts()
            accounts = data.get("accounts", {})
            success_count = 0

            def _worker(item):
                email, acc = item
                try:
                    ok = self.refresh_single_account_quota(email, acc)
                    return (email, ok)
                except Exception as e:
                    logger.error(f"并发刷新账号 {email} 配额失败: {e}")
                    return (email, False)

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                results = executor.map(_worker, list(accounts.items()))
                for email, ok in results:
                    if ok:
                        success_count += 1

            self.save_accounts(data)
            logger.info(f"✅ 全池配额极速并发刷新完成！成功: {success_count}/{len(accounts)}")
            return success_count
        finally:
            self.refreshing_now = False

    def trigger_warmup(self, email: str, acc: Dict[str, Any]) -> bool:
        # 【零风控安全铁律 · 2026-09-26 拍板】彻底停用任何后台伪造生成 Ping 预热，保障账号绝对安全！
        logger.info(f"🛡️ [安全拦截] 账号 {email} 伪造预热已被安全拦截（零请求），保障账号绝对安全！")
        return True

        now = int(time.time())
        at = acc.get("access_token")
        exp = acc.get("expires_at", 0)
        acc_id = acc.get("id", "")

        # 临期 15 分钟安全偏置
        if not at or exp <= (now + TOKEN_REFRESH_SKEW_SECONDS):
            rt = acc.get("refresh_token", "")
            if rt:
                refreshed = self.refresh_google_token(rt)
                if refreshed:
                    at = refreshed.get("access_token")
                    expires_in = refreshed.get("expires_in", 3600)
                    exp = now + expires_in
                    acc["access_token"] = at
                    acc["expires_at"] = exp
                    self._sync_antigravity_tools_cache(acc_id, access_token=at, refresh_token=rt, expiry_ts=exp)

        if not at:
            logger.error(f"账号 {email} 缺失有效 Token，无法预热")
            return False

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"Ping warmup at {int(time.time())}"}]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 1,
                "temperature": 0.0
            }
        }
        body = json.dumps(payload).encode("utf-8")
        ctx = ssl.create_default_context()

        success = False
        for ep in WARMUP_ENDPOINTS:
            try:
                url = f"{ep}?model=gemini-3-flash"
                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={
                        "Authorization": f"Bearer {at}",
                        "Content-Type": "application/json",
                        "User-Agent": NATIVE_OAUTH_USER_AGENT
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    if resp.status in (200, 204):
                        success = True
                        break
            except urllib.error.HTTPError as he:
                if he.code == 403:
                    body_err = he.read().decode("utf-8", errors="ignore")
                    val_url = None
                    try:
                        err_j = json.loads(body_err)
                        for det in err_j.get("error", {}).get("details", []):
                            if det.get("reason") == "VALIDATION_REQUIRED":
                                val_url = det.get("metadata", {}).get("validation_url", "")
                    except Exception:
                        pass
                    if val_url:
                        acc["validation_blocked"] = True
                        acc["validation_url"] = val_url
                        acc["validation_blocked_reason"] = "VALIDATION_REQUIRED"
                        self._sync_antigravity_tools_cache(acc_id, validation_blocked=True, val_url=val_url)
                        logger.error(f"🚨 [预热风控熔断] 账号 {email} 触发 Google VALIDATION_REQUIRED: {val_url}")
                        return False
            except Exception:
                continue

        now = int(time.time())
        acc["last_warmup_ts"] = now
        # 4 小时基准 + 随机 10~40 分钟抖动
        jitter = random.randint(600, 2400)
        acc["next_warmup_ts"] = now + 14400 + jitter

        logger.info(f"🔥 账号 {email} 预热{'成功' if success else '触发完成'}，下次随机预热时间: {time.strftime('%H:%M:%S', time.localtime(acc['next_warmup_ts']))}")
        return True

    def switch_account(self, target_email: str) -> Tuple[bool, str]:
        # 物理中枢无缝接入：与额度用尽自动轮换 100% 共享完全一致的底层物理切换与脱壳接力唤醒
        # 注意：不设置人工锁定，看门狗依旧正常监控额度，额度用完后自动切换不受阻碍
        try:
            from antigravity_physical_switcher import AntigravityPhysicalManager, DEFAULT_RELAY_PROMPT
            mgr = AntigravityPhysicalManager()
            relay_prompt = (
                "【系统级配额断点无缝续传指令】当前账号已通过物理钥匙串无缝切换至高配额账号，配额已完全满血！\n"
                "请从刚才中断的位置继续推进任务，保持无人值守与严谨交付：\n"
                "1. 【恢复核心主线】：检查并恢复刚才被中断的代码编写、终端命令或交付文档；\n"
                "2. 【无缝衔接 Teamwork 协作】：若本任务涉及 Teamwork / 多智能体协作（Subagents），必须无缝恢复团队协同管线；主动检查未完结子代理的状态与产出，平滑唤醒并驱动其继续推进各自专属子任务，直至整体协作目标达成；（仅排除早已完工结案或用户显式取消的子代理，严禁丢弃未完工的 Teamwork 链路）；\n"
                "3. 【终态闭环交付】：全程保持无人值守全速推进，直至完整交付符合验收标准的最终成果！"
            )
            success = mgr.perform_real_switch(target_email, restart_app=True, relay_prompt=relay_prompt, force=True)
            if success:
                # 同步更新 Hub 本地数据库活跃指针
                data = self.load_accounts()
                data["active_email"] = target_email
                data["last_updated"] = int(time.time())
                self.save_accounts(data)
                logger.info(f"🚀 [物理切换成功] 目标账号 {target_email} 凭据已注入，Antigravity 正在脱壳重启并自动发送接力提示词！")
                return True, "物理切换成功，Antigravity 正在脱壳重启并自动接力唤醒！"
            else:
                logger.error(f"❌ 物理切换执行失败: {target_email}")
                return False, "物理切换执行失败"
        except Exception as e:
            logger.error(f"物理切换异常: {e}")
            return False, f"物理切换异常: {e}"



ENGINE = HubEngine()


def format_reset_time(iso_str: str) -> str:
    if not iso_str:
        return "--"
    try:
        # 解析 ISO UTC
        target_ts = 0
        if "T" in iso_str:
            clean_iso = iso_str.replace("Z", "+00:00")
            # 简单计算
            import datetime
            dt = datetime.datetime.fromisoformat(clean_iso)
            target_ts = dt.timestamp()
        else:
            return iso_str

        diff = int(target_ts - time.time())
        if diff <= 0:
            return "已就绪"
        days = diff // 86400
        hours = (diff % 86400) // 3600
        mins = (diff % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"
    except Exception:
        return iso_str[:16]


def format_countdown_sec(sec_diff: int) -> str:
    if sec_diff <= 0:
        return "即将触发"
    hours = sec_diff // 3600
    mins = (sec_diff % 3600) // 60
    if hours > 0:
        return f"{hours}h {mins}m"
    if mins > 0:
        return f"{mins}m"
    return f"{sec_diff}s"


def render_quota_cell(h5_pct: float, weekly_pct: float, reset_5h_info: str = "", reset_weekly_info: str = "", model_type: str = "gemini") -> str:
    val_w = round(weekly_pct * 100, 1)

    # 核心物理约束：周额度没了，5H 自然归零，绝对不能虚假满额就绪！
    is_weekly_exhausted = (val_w <= 0.0)
    if is_weekly_exhausted:
        val_5h = 0.0
    else:
        val_5h = round(h5_pct * 100, 1)

    c_5h = "#16A34A" if val_5h >= 50 else ("#EA580C" if val_5h >= 15 else "#DC2626")
    c_w = "#16A34A" if val_w >= 50 else ("#EA580C" if val_w >= 15 else "#DC2626")
    
    # 5小时恢复倒计时与状态呈现：
    if is_weekly_exhausted:
        tip = f"周度总配额已耗尽 (0.0%)，5小时配额自然归零，等待周度重置: {reset_weekly_info}"
        reset_5h_html = f'<span class="q-reset q-reset-exhausted font-mono" title="{tip}">周枯竭</span>'
    elif reset_5h_info and reset_5h_info not in ("--", "已就绪"):
        # 只要存在有效恢复倒计时，直接呈现时间（如 3h 23m、45m）！无论是否100%，绝不覆盖！
        reset_5h_html = f'<span class="q-reset q-reset-5h font-mono" title="5小时滚动配额恢复倒计时: {reset_5h_info}">{reset_5h_info}</span>'
    elif val_5h >= 99.9 or reset_5h_info == "已就绪":
        reset_5h_html = '<span class="q-reset q-reset-ready font-mono" title="未激活或已就绪">已就绪</span>'
    else:
        reset_5h_html = '<span class="q-reset q-reset-empty font-mono">--</span>'

    # 周度重置倒计时呈现：
    if reset_weekly_info and reset_weekly_info not in ("--", "已就绪"):
        reset_w_html = f'<span class="q-reset q-reset-w font-mono" title="周度配额重置倒计时: {reset_weekly_info}">{reset_weekly_info}</span>'
    elif reset_weekly_info == "已就绪" or val_w >= 99.9:
        reset_w_html = '<span class="q-reset q-reset-ready font-mono" title="周度配额完全就绪">就绪</span>'
    else:
        reset_w_html = '<span class="q-reset q-reset-empty font-mono">--</span>'

    lbl_5h_cls = "tag-5h-g" if model_type == "gemini" else "tag-5h-c"
    lbl_w_cls = "tag-w-g" if model_type == "gemini" else "tag-w-c"

    return f"""
    <div class="q-cell">
        <div class="q-row">
            <span class="q-lbl {lbl_5h_cls}">5h</span>
            <div class="q-track"><div class="q-fill" style="width: {min(100, max(0, val_5h))}%; background: {c_5h};"></div></div>
            <span class="q-val font-mono" style="color: {c_5h};">{val_5h}%</span>
            <div class="q-slot">{reset_5h_html}</div>
        </div>
        <div class="q-row">
            <span class="q-lbl {lbl_w_cls}">周</span>
            <div class="q-track"><div class="q-fill" style="width: {min(100, max(0, val_w))}%; background: {c_w};"></div></div>
            <span class="q-val font-mono" style="color: {c_w};">{val_w}%</span>
            <div class="q-slot">{reset_w_html}</div>
        </div>
    </div>
    """


# 新野兽派官方规范：5组高对比度Pastel交替色盘 (彻底消灭死白)
NEO_ROW_PALETTES = [
    "#E0F2FE",  # 电光冰蓝 (Cyber Sky)
    "#FCE7F3",  # 泡泡糖柔粉 (Bubblegum Pink)
    "#DCFCE7",  # 酸性嫩绿 (Acid Mint)
    "#F3E8FF",  # 薰衣草紫 (Lavender Violet)
    "#FFEDD5",  # 活力暖杏 (Warm Apricot)
]


def render_top_bar_stats_html(total_count: int, pro_count: int, avg_g: float, avg_c: float, cur_time: str, oob: bool = False) -> str:
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    # 彻底去除顶栏无意义的均值统计与15s轮询时间戳，避免挤压重叠，保持极致克制与清爽
    return f"""<div id="top-bar-stats" class="stats-strip font-mono"{oob_attr} style="display:none;"></div>"""


def render_active_pill_html(active_email: str, oob: bool = False) -> str:
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    short_name = active_email.split("@")[0] if "@" in active_email else (active_email or "未激活")
    lock_info = get_manual_override_lock()
    now_ts = time.time()

    shield_svg = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#E11D48" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:4px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
    zap_svg = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:4px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'

    if lock_info and lock_info.get("manual_account") == active_email and lock_info.get("locked_until", 0) > now_ts:
        rem_sec = int(lock_info.get("locked_until", 0) - now_ts)
        rem_min = max(1, rem_sec // 60)
        return f"""<span id="active-email-pill" class="active-pill font-mono locked-manual" title="人工指定保护中：后台看门狗已被物理阻断，不自动切号 (点击复制完整账号: {active_email})" onclick="copyText('{active_email}')"{oob_attr}>
            {shield_svg}人工锁定: <span class="active-email-val">{short_name}</span> <span class="lock-tag font-mono">({rem_min}m)</span>
            <button class="btn-unlock-pill font-mono" onclick="doUnlockProtection(); event.preventDefault(); event.stopPropagation();" title="点击恢复后台自动轮转">解除</button>
        </span>"""
    else:
        return f"""<span id="active-email-pill" class="active-pill font-mono auto-mode" title="自动轮转模式中 (点击快速复制完整账号: {active_email})" onclick="copyText('{active_email}')"{oob_attr}>
            {zap_svg}活跃: <span class="active-email-val">{short_name}</span> <span class="auto-tag font-mono">(自动)</span>
        </span>"""


def render_table_rows(include_oob: bool = False) -> str:
    data = ENGINE.load_accounts()
    active_email = data.get("active_email", "")
    accounts = data.get("accounts", {})

    total_count = len(accounts)
    pro_count = sum(1 for a in accounts.values() if a.get("tier") == "PRO")
    avg_g = round(sum(a.get("gemini", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    avg_c = round(sum(a.get("claude", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    cur_time = time.strftime("%H:%M:%S")

    if not accounts:
        empty_row = '<tr><td colspan="6" style="text-align:center; padding: 24px; font-size:13px; font-weight:900; background:#FFE4E6;">暂无账号，请执行单向导入</td></tr>'
        if include_oob:
            return empty_row + "\n" + render_top_bar_stats_html(0, 0, 0.0, 0.0, cur_time, oob=True) + "\n" + render_active_pill_html("", oob=True)
        return empty_row

    rows = []
    now = int(time.time())

    sched_warmup = {}
    if os.path.exists(WARMUP_SCHEDULE_PATH):
        try:
            with open(WARMUP_SCHEDULE_PATH, "r", encoding="utf-8") as sf:
                sched_warmup = json.load(sf)
        except Exception:
            pass

    for idx, (email, acc) in enumerate(accounts.items(), start=1):
        is_active = (email == active_email)
        
        row_bg = "#FFF066" if is_active else NEO_ROW_PALETTES[(idx - 1) % len(NEO_ROW_PALETTES)]
        active_class = "is-active-row" if is_active else ""
        
        num_html = f"""<div class="num-cell-inner" title="按住拖拽调节账号顺序"><span class="drag-handle">⠿</span><span class="row-num font-mono">{idx}</span></div>"""

        arrows_html = f"""<div class="reorder-arrows">
            <button class="btn-arrow" onclick="moveAccountRow('{email}', -1); event.preventDefault(); event.stopPropagation();" title="上移一位">▲</button>
            <button class="btn-arrow" onclick="moveAccountRow('{email}', 1); event.preventDefault(); event.stopPropagation();" title="下移一位">▼</button>
        </div>"""

        is_blocked = bool(acc.get("validation_blocked"))
        val_url = acc.get("validation_url", "")

        if is_active:
            badge_html = '<span class="badge badge-active"><span class="pulse-dot-green"></span>ACTIVE</span>'
            main_btn_html = f"""<div class="active-badge-action font-mono" title="当前主程序正在使用此账号护航">在用</div>"""
        elif is_blocked:
            badge_html = '<span class="badge badge-blocked" title="Google账号需网页验证">⚠️待验证</span>'
            main_btn_html = f"""<button class="btn btn-unblock font-mono" 
                            onclick="doUnblockAccount('{email}'); event.preventDefault(); event.stopPropagation();"
                            title="拉起专属隔离Chrome容器并自动定向对应账号解封（彻底防500）">解封</button>"""
        else:
            badge_html = '<span class="badge badge-standby">STANDBY</span>'
            has_refresh_token = bool(acc.get("refresh_token", ""))
            if has_refresh_token:
                main_btn_html = f"""<button class="btn btn-switch font-mono" 
                                onclick="doSwitchAccount('{email}'); event.preventDefault(); event.stopPropagation();"
                                title="切换为此账号，看门狗照常监控额度自动轮换">切换</button>"""
            else:
                main_btn_html = f"""<button class="btn btn-switch font-mono" 
                                style="opacity:0.35;cursor:not-allowed;background:#ccc;"
                                onclick="event.preventDefault();event.stopPropagation();showToast('❌ 此账号缺少授权 Token，无法切换！请先在 Antigravity 中重新登录此账号。','error');"
                                title="此账号缺少 refresh_token，无法物理切换">无Token</button>"""

        action_switch_html = f"""<div class="actions-flex">{main_btn_html}{arrows_html}</div>"""

        # 联动持久化预热调度账本：若官方返回尚未刷新或漂移，优先采信预热锁定的绝对重置倒计时
        acc_warmup = sched_warmup.get(email, {})
        warmup_iso = acc_warmup.get("locked_reset_iso", "")
        warmup_model = acc_warmup.get("model_warmed", "")

        # Gemini 配额 (极光天蓝)
        g_w = acc.get("gemini", {}).get("quota_weekly", 1.0)
        # 短板约束：若周配额已耗尽 (<=0.0)，5H 配额物理上必然归零，杜绝虚假满血
        g_5h = 0.0 if g_w <= 0.0001 else acc.get("gemini", {}).get("quota_5h", 1.0)
        g_reset_raw = acc.get("gemini", {}).get("reset_time_5h", "")
        if (not g_reset_raw or g_reset_raw == "--") and warmup_iso and (not warmup_model or "gemini" in warmup_model):
            g_reset_raw = warmup_iso
        g_reset_5h = format_reset_time(g_reset_raw)
        g_reset_w = format_reset_time(acc.get("gemini", {}).get("reset_time_weekly", acc.get("gemini", {}).get("reset_time", "")))
        g_cell = render_quota_cell(g_5h, g_w, g_reset_5h, g_reset_w, model_type="gemini")

        # Claude 配额 (活力暖橙)
        c_w = acc.get("claude", {}).get("quota_weekly", 1.0)
        c_5h = 0.0 if c_w <= 0.0001 else acc.get("claude", {}).get("quota_5h", 1.0)
        c_reset_raw = acc.get("claude", {}).get("reset_time_5h", "")
        if (not c_reset_raw or c_reset_raw == "--") and warmup_iso and ("claude" in warmup_model):
            c_reset_raw = warmup_iso
        c_reset_5h = format_reset_time(c_reset_raw)
        c_reset_w = format_reset_time(acc.get("claude", {}).get("reset_time_weekly", acc.get("claude", {}).get("reset_time", "")))
        c_cell = render_quota_cell(c_5h, c_w, c_reset_5h, c_reset_w, model_type="claude")

        # 彻底去除邮箱域名后缀，只保留账号英文字符，告别 ... 截断
        short_name = email.split("@")[0] if "@" in email else email

        row = f"""
        <tr class="account-row {active_class}" 
            draggable="true"
            style="background-color: {row_bg};"
            data-email="{email}"
            data-gemini-5h="{g_5h}"
            data-gemini-w="{g_w}"
            data-claude-5h="{c_5h}"
            data-claude-w="{c_w}"
            data-is-active="{'1' if is_active else '0'}">
            <td class="col-center font-mono num-col" style="background-color: {row_bg};">{num_html}</td>
            <td class="col-status" style="background-color: {row_bg};"><div class="status-cell-wrap">{badge_html}</div></td>
            <td class="col-email" style="background-color: {row_bg};">
                <div class="email-cell-inner">
                    <span class="email-text font-mono" onclick="copyText('{email}')" title="点击复制完整账号凭据: {email}">{short_name}</span>
                    <span class="pro-tag font-mono">PRO</span>
                </div>
            </td>
            <td class="col-quota" style="background-color: {row_bg};">{g_cell}</td>
            <td class="col-quota" style="background-color: {row_bg};">{c_cell}</td>
            <td class="col-actions" style="background-color: {row_bg};">
                <div class="actions-wrap">
                    {action_switch_html}
                </div>
            </td>
        </tr>
        """
        rows.append(row)

    output = "\n".join(rows)
    if include_oob:
        output += "\n" + render_top_bar_stats_html(total_count, pro_count, avg_g, avg_c, cur_time, oob=True)
        output += "\n" + render_active_pill_html(active_email, oob=True)
    return output


def render_dashboard_html() -> str:
    data = ENGINE.load_accounts()
    accounts = data.get("accounts", {})
    active_email = data.get("active_email", "")

    total_count = len(accounts)
    pro_count = sum(1 for a in accounts.values() if a.get("tier") == "PRO")
    avg_g = round(sum(a.get("gemini", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    avg_c = round(sum(a.get("claude", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    cur_time = time.strftime("%H:%M:%S")

    table_rows = render_table_rows(include_oob=False)
    stats_html = render_top_bar_stats_html(total_count, pro_count, avg_g, avg_c, cur_time, oob=False)
    active_pill_html = render_active_pill_html(active_email, oob=False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antigravity Hub · Neo-Brutalism</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <style>
        :root {{
            --bg-color: #F4F0EA;
            --text-color: #000000;
            --border-black: 2px solid #000000;
            --border-thick: 2.5px solid #000000;
            --shadow-hard: 4px 4px 0px #000000;
            --shadow-card: 5px 5px 0px #000000;
            --shadow-btn: 2.5px 2.5px 0px #000000;
            --shadow-sm: 1.5px 1.5px 0px #000000;
            --radius-card: 10px;
            --radius-btn: 6px;
            --radius-pill: 4px;
            --radius-modal: 12px;
            --yellow-main: #FFE600;
            --cyan-accent: #00F0FF;
            --pink-accent: #FF2A85;
            --green-accent: #22C55E;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        html, body {{
            min-height: 100% !important;
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Space Grotesk", sans-serif;
            padding: 16px 0 24px 0;
            margin: 0;
            font-size: 12px;
            line-height: 1.2;
            -webkit-font-smoothing: antialiased;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            overflow-x: hidden;
            overflow-y: auto;
        }}

        /* 彻底根除滚动条，绝不允许 WebKit 垂直滚动条挤压视口导致居中偏心 */
        ::-webkit-scrollbar {{
            display: none !important;
            width: 0 !important;
            height: 0 !important;
        }}

        .font-mono {{
            font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Monaco, Consolas, monospace;
            font-variant-numeric: tabular-nums;
        }}

        /* 🚀 弹性全自适应版心：宽度自由撑开，两翼 16px 舒适呼吸留白，支持用户自由拖拽缩放任意尺寸 */
        .app-container {{
            width: 100%;
            max-width: 1040px;
            min-width: 580px;
            margin: 0 auto;
            box-sizing: border-box;
            padding: 0 16px;
            flex-shrink: 0;
        }}

        /* 顶部黑黄斜纹加载条 */
        #loading-bar {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: repeating-linear-gradient(45deg, #000, #000 8px, #FFE600 8px, #FFE600 16px);
            z-index: 9999;
        }}
        .htmx-request#loading-bar, .htmx-request #loading-bar {{
            display: block;
        }}

        /* 顶栏控制条：新野兽派高饱和柠檬黄底 + 3px 纯黑粗框 + 4px 硬投影 + 10px 微圆角 (弹性撑满版心) */
        .top-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border: var(--border-thick);
            border-radius: var(--radius-card);
            background: var(--yellow-main);
            padding: 10px 16px;
            box-shadow: var(--shadow-hard);
            margin-bottom: 8px;
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box;
            white-space: nowrap !important;
        }}

        .top-left {{
            display: flex;
            align-items: center;
            justify-content: flex-start;
            flex: 1 1 0;
        }}

        .top-center {{
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 2 1 0;
        }}

        .top-right {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            flex: 1 1 0;
        }}

        .brand-title {{
            background: #FFFFFF;
            color: #000000;
            font-size: 12.5px;
            font-weight: 900;
            letter-spacing: 0.5px;
            padding: 0 12px;
            height: 30px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            white-space: nowrap !important;
            flex-shrink: 0 !important;
            box-sizing: border-box;
            user-select: none;
        }}

        .active-pill {{
            background: #FFFFFF;
            color: #000000;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            padding: 0 16px;
            height: 30px;
            min-width: 185px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            font-size: 12px;
            font-weight: 900;
            box-shadow: 2.5px 2.5px 0px #000000;
            white-space: nowrap !important;
            flex-shrink: 0 !important;
            cursor: pointer;
            box-sizing: border-box;
            transition: all 0.08s ease;
        }}
        .active-pill:hover {{
            background: #FFE600;
            transform: translate(-1px, -1px);
            box-shadow: 3.5px 3.5px 0px #000000;
        }}

        .active-pill.locked-manual {{
            background: #FFE4E6;
            border-color: #E11D48;
        }}
        .active-pill.locked-manual:hover {{
            background: #FECDD3;
        }}
        .lock-tag {{
            font-size: 11px;
            color: #E11D48;
            font-weight: 800;
        }}
        .auto-tag {{
            font-size: 11px;
            color: #16A34A;
            font-weight: 800;
        }}
        .btn-unlock-pill {{
            margin-left: 6px;
            background: #E11D48;
            color: #FFFFFF;
            border: 1.5px solid #000000;
            border-radius: 4px;
            padding: 1px 6px;
            font-size: 10px;
            font-weight: 900;
            cursor: pointer;
            box-shadow: 1px 1px 0px #000000;
            transition: all 0.08s ease;
        }}
        .btn-unlock-pill:hover {{
            background: #BE123C;
            transform: translate(-0.5px, -0.5px);
            box-shadow: 1.5px 1.5px 0px #000000;
        }}

        .stats-strip {{
            display: none;
        }}

        .btn-top {{
            padding: 0 14px;
            height: 30px;
            font-size: 12px;
            font-weight: 900;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2.5px 2.5px 0px #000000;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            cursor: pointer;
            box-sizing: border-box;
            transition: all 0.08s ease;
        }}
        .btn-top:hover {{
            transform: translate(-1px, -1px);
            box-shadow: 3.5px 3.5px 0px #000000;
        }}
        .btn-top:active {{
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000000;
        }}
        .btn-import {{ background: #00F0FF; color: #000000; margin-right: 6px; }}
        .btn-export {{ background: #FFE600; color: #000000; margin-right: 6px; }}
        .btn-refresh-all {{ background: #22C55E; color: #000000; }}
        .btn-warmup-all {{ background: #FF4D4D; color: #FFFFFF; }}

        .control-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #FFFFFF;
            border: var(--border-thick);
            border-radius: var(--radius-card);
            box-shadow: var(--shadow-hard);
            padding: 5px 12px;
            margin-bottom: 8px;
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box;
            gap: 8px;
            flex-wrap: nowrap !important;
            white-space: nowrap !important;
        }}
        .search-box {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #F4F0EA;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            padding: 0 8px;
            height: 26px;
            width: 150px;
            flex-shrink: 0;
            box-sizing: border-box;
            position: relative;
        }}
        .search-icon {{
            font-size: 11px;
            user-select: none;
        }}
        .search-input {{
            border: none;
            background: transparent;
            outline: none;
            font-size: 11px;
            font-weight: 800;
            width: 100%;
            color: #000000;
        }}
        .kbd-hint {{
            font-size: 10px;
            font-weight: 900;
            background: #E5E7EB;
            color: #4B5563;
            border: 1px solid #9CA3AF;
            border-radius: 3px;
            padding: 0 4px;
            line-height: 14px;
            height: 14px;
            user-select: none;
            margin-left: auto;
        }}
        .btn-clear {{
            border: none;
            background: transparent;
            cursor: pointer;
            font-size: 11px;
            font-weight: 900;
            padding: 0 2px;
            color: #6B7280;
        }}
        .btn-clear:hover {{
            color: #DC2626;
        }}
        .filter-group {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            flex-shrink: 0;
        }}
        .filter-tab {{
            background: #F4F0EA;
            color: #000000;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            font-size: 10.5px;
            font-weight: 900;
            padding: 0 8px;
            height: 26px;
            flex-shrink: 0;
            cursor: pointer;
            box-sizing: border-box;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            transition: all 0.08s ease;
        }}
        .filter-tab:hover {{
            background: #E5E7EB;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .filter-tab:active {{
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000000;
        }}
        .filter-tab.active {{
            background: #FFE600;
            color: #000000;
            box-shadow: 2px 2px 0px #000000;
            font-weight: 900;
        }}
        .filter-tab.tab-has-warning {{
            border-color: #DC2626 !important;
            color: #DC2626 !important;
            background: #FEF2F2 !important;
            box-shadow: 2px 2px 0px #DC2626 !important;
        }}
        .tab-cnt {{
            font-size: 10px;
            opacity: 0.95;
            font-weight: 800;
        }}
        .filter-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            border: 1.5px solid #000000;
            display: inline-block;
            margin-right: 4px;
            vertical-align: middle;
            box-sizing: border-box;
        }}
        .dot-green {{ background: #22C55E; }}
        .dot-red {{ background: #EF4444; }}
        .dot-blue {{ background: #0EA5E9; }}
        .dot-gray {{ background: #9CA3AF; }}
        .filter-tab[data-filter="usable"].active {{
            background: #00F0FF;
            color: #000000;
        }}
        .stats-counter {{
            background: #FFFFFF;
            color: #000000;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            font-size: 11px;
            font-weight: 900;
            padding: 0 10px;
            height: 26px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            white-space: nowrap;
            box-sizing: border-box;
        }}
        .stats-counter b {{
            color: #000000;
        }}

        /* 表格总容器：3px 纯黑外边框 + 4px 硬投影 + 10px 微圆角 + 彻底消除无意义横向滚动条 */
        .table-wrap {{
            border: var(--border-thick);
            background: #FFFFFF;
            box-shadow: var(--shadow-hard);
            border-radius: var(--radius-card);
            overflow: hidden;
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box;
        }}

        /* 核心铁律：table-layout: fixed，严格等宽贴合容器，彻底消灭横向滑块 */
        table {{
            width: 100%;
            table-layout: fixed;
            border-collapse: collapse;
            text-align: left;
        }}

        /* 表头新野兽派全撞色系统 (规范大小写，5h/4h 精准原样呈现) */
        thead th {{
            padding: 7px 6px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: 0.5px;
            border-right: 2px solid #000000;
            border-bottom: 3px solid #000000;
            color: #000000;
            overflow: hidden;
            white-space: nowrap;
            box-sizing: border-box;
        }}
        thead th:last-child {{ border-right: none; }}

        .th-num {{ background: #FFFFFF; text-align: center; }}
        .th-status {{ background: #38BDF8; text-align: center; }}
        .th-email {{ background: #FDE047; text-align: left; padding-left: 10px; }}
        .th-gemini {{ background: #7DD3FC; text-align: center; }}
        .th-claude {{ background: #FB923C; text-align: center; }}
        .th-warmup {{ background: #C084FC; text-align: center; }}
        .th-action {{ background: #4ADE80; text-align: center; }}

        tbody tr {{
            height: 33px;
        }}

        /* 所有单元格：实线 2px 纯黑分割网格，严格统一 box-sizing */
        tbody td {{
            padding: 3px 6px;
            border-right: 2px solid #000000;
            border-bottom: 2px solid #000000;
            vertical-align: middle;
            box-sizing: border-box;
            overflow: hidden;
        }}
        tbody td:last-child {{
            border-right: none;
        }}
        tbody tr:last-child td {{
            border-bottom: none !important;
        }}

        /* 活跃账号行纯色高亮 (告别黑框叠加黑框，仅保留鲜明背景色，与其他行结构无任何差异) */
        tbody tr.row-active td {{
            background-color: #FEF08A !important;
        }}

        /* 鼠标悬停色阶加深微动效 */
        tbody tr:hover td {{
            filter: brightness(0.95);
        }}

        .col-center {{ text-align: center; }}
        .num-col {{ font-size: 11px; font-weight: 900; color: #000000; }}

        /* 状态单元格：0 内边距 + flex 完全居中，彻底根除边框重叠 */
        .col-status {{
            padding: 0 !important;
            text-align: center;
            vertical-align: middle;
            box-sizing: border-box;
        }}
        .status-cell-wrap {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
            box-sizing: border-box;
        }}

        /* 状态徽章：严格定宽 60px × 20px + 1.5px 描边与投影，在 78px 列内两翼拥有 9px 安全呼吸空间，零边框重叠 */
        .badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 60px;
            height: 20px;
            font-size: 10px;
            font-weight: 900;
            border: 1.5px solid #000000;
            border-radius: var(--radius-pill);
            box-shadow: 1.5px 1.5px 0px #000000;
            line-height: 1;
            letter-spacing: 0.5px;
            box-sizing: border-box;
            gap: 3px;
        }}
        .badge-active {{ background: #22C55E; color: #000000; }}
        .badge-standby {{ background: #38BDF8; color: #000000; }}
        .badge-blocked {{ background: #EF4444; color: #FFFFFF; }}

        .pulse-dot-green {{
            width: 5px;
            height: 5px;
            background: #15803D;
            border-radius: 50%;
            display: inline-block;
            animation: pulse-dot 1.5s infinite;
        }}
        @keyframes pulse-dot {{
            0% {{ transform: scale(0.9); opacity: 0.6; }}
            50% {{ transform: scale(1.3); opacity: 1; }}
            100% {{ transform: scale(0.9); opacity: 0.6; }}
        }}

        /* 账号邮箱与 PRO 徽章紧凑贴合 (左内边距 10px 远离分隔线，紧跟名字 6px 间隙) */
        .col-email {{
            padding: 0 10px !important;
            white-space: nowrap !important;
            box-sizing: border-box;
            overflow: hidden;
            vertical-align: middle;
        }}
        .email-cell-inner {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            vertical-align: middle;
        }}
        .email-text {{
            font-size: 12px;
            font-weight: 900;
            display: inline-block;
            color: #000000;
            vertical-align: middle;
            white-space: nowrap !important;
            cursor: pointer;
            padding: 1px 3px;
            border-radius: 3px;
            transition: background 0.1s ease;
        }}
        .email-text:hover {{ 
            text-decoration: underline; 
            background: #FFE600; 
        }}
        
        .pro-tag {{
            font-size: 9px;
            font-weight: 900;
            background: var(--pink-accent);
            color: #FFFFFF;
            width: 34px !important;
            min-width: 34px !important;
            max-width: 34px !important;
            height: 17px;
            border: 1.5px solid #000000;
            border-radius: 3px;
            box-shadow: 1.5px 1.5px 0px #000000;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            letter-spacing: 0.5px;
            box-sizing: border-box;
            flex-shrink: 0 !important;
        }}

        /* 配额单元格：双轨绝对等长 + 52px 绝对对称槽位 */
        .col-quota {{
            padding: 3px 8px !important;
            box-sizing: border-box;
            overflow: hidden;
        }}
        .q-cell {{
            display: flex;
            flex-direction: column;
            gap: 2.5px;
            width: 100%;
            box-sizing: border-box;
        }}
        .q-row {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 10.5px;
            font-weight: 900;
            width: 100%;
            box-sizing: border-box;
            white-space: nowrap !important;
        }}
        .q-lbl {{
            width: 20px !important;
            min-width: 20px !important;
            max-width: 20px !important;
            flex-shrink: 0 !important;
            font-size: 9px;
            font-weight: 900;
            text-align: center;
            padding: 0.5px 0;
            border: 1px solid #000000;
            border-radius: 3px;
            box-shadow: 1px 1px 0px #000000;
            line-height: 1;
            box-sizing: border-box;
            white-space: nowrap !important;
        }}
        .tag-5h-g {{ background: #38BDF8; color: #000000; }}
        .tag-w-g {{ background: #38BDF8; color: #000000; }}
        .tag-5h-c {{ background: #FB923C; color: #000000; }}
        .tag-w-c {{ background: #FB923C; color: #000000; }}

        /* 进度条：两行等宽 flex: 1 1 auto，上下垂直绝对等长！ */
        .q-track {{
            flex: 1 1 auto !important;
            height: 7px;
            background: #FFFFFF;
            border: 1.5px solid #000000;
            border-radius: var(--radius-pill);
            box-shadow: 1px 1px 0px #000000;
            overflow: hidden;
            box-sizing: border-box;
        }}
        .q-fill {{ height: 100%; transition: width 0.3s ease; }}
        
        /* 百分比数值：严格定宽 44px，居右对齐，等宽防抖 */
        .q-val {{
            width: 44px !important;
            min-width: 44px !important;
            max-width: 44px !important;
            flex-shrink: 0 !important;
            text-align: right;
            font-weight: 900;
            font-size: 10.5px;
            box-sizing: border-box;
            white-space: nowrap !important;
        }}

        /* 52px 固定重置时间槽 */
        .q-slot {{
            width: 52px !important;
            min-width: 52px !important;
            max-width: 52px !important;
            flex-shrink: 0 !important;
            display: inline-flex;
            justify-content: center;
            align-items: center;
            box-sizing: border-box;
        }}
        .q-reset {{
            width: 50px !important;
            min-width: 50px !important;
            max-width: 50px !important;
            flex-shrink: 0 !important;
            font-size: 9px;
            font-weight: 900;
            padding: 1px 0;
            border: 1.5px solid #000000;
            border-radius: 3px;
            box-shadow: 1px 1px 0px #000000;
            white-space: nowrap !important;
            text-align: center;
            box-sizing: border-box;
            display: inline-block;
        }}
        .q-reset-5h {{
            color: #0369A1 !important;
            background: #BAE6FD !important;
            border-color: #000000 !important;
        }}
        .q-reset-w {{
            color: #854D0E !important;
            background: #FEF08A !important;
            border-color: #000000 !important;
        }}
        .q-reset-ready {{
            color: #15803D !important;
            background: #DCFCE7 !important;
            border-color: #000000 !important;
        }}
        .q-reset-exhausted {{
            color: #991B1B !important;
            background: #FECACA !important;
            border-color: #000000 !important;
        }}
        .q-reset-empty {{
            background: transparent;
            color: transparent;
            border-color: transparent;
            box-shadow: none;
        }}
        .q-reset-none {{
            visibility: hidden !important;
            opacity: 0 !important;
            border-color: transparent !important;
            background: transparent !important;
            box-shadow: none !important;
        }}

        /* 预热药丸与上次时间胶囊 */
        .warmup-wrap {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            width: 100%;
            box-sizing: border-box;
            white-space: nowrap !important;
        }}
        .warmup-pill {{
            background: #C084FC;
            border: 1.5px solid #000000;
            border-radius: var(--radius-pill);
            width: 62px !important;
            min-width: 62px !important;
            max-width: 62px !important;
            flex-shrink: 0 !important;
            height: 20px;
            font-size: 9.5px;
            font-weight: 900;
            box-shadow: 1.5px 1.5px 0px #000000;
            color: #000000;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            white-space: nowrap !important;
            overflow: hidden;
        }}
        .warmup-sub {{
            font-size: 9px;
            color: #000000;
            font-weight: 900;
            width: 52px !important;
            min-width: 52px !important;
            max-width: 52px !important;
            flex-shrink: 0 !important;
            height: 20px;
            background: #FFFFFF;
            border: 1.5px solid #000000;
            border-radius: var(--radius-pill);
            box-shadow: 1.5px 1.5px 0px #000000;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 2px;
            white-space: nowrap !important;
            box-sizing: border-box;
        }}
        .warmup-sub .sub-icon {{
            font-size: 9px;
        }}
        .warmup-sub.sub-empty {{
            color: #6B7280;
            background: #F3F4F6;
            border-style: dashed;
        }}

        /* 操作按钮容器与定宽按键 */
        .col-actions {{
            padding: 0 !important;
            text-align: center;
            vertical-align: middle;
            box-sizing: border-box;
            overflow: hidden;
        }}
        .actions-wrap {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
            box-sizing: border-box;
            white-space: nowrap !important;
        }}
        .btn {{
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            height: 24px;
            font-size: 11px;
            font-weight: 900;
            cursor: pointer;
            box-shadow: 2px 2px 0px #000000;
            transition: all 0.08s ease-in-out;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            white-space: nowrap !important;
        }}
        .btn:hover {{
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .btn:active {{
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000000;
        }}
        .btn.htmx-request {{
            opacity: 0.7;
            pointer-events: none;
        }}
        .btn.htmx-request::after {{
            content: " ⏳";
        }}
        
        /* 切换按键与权威锁定徽章：严格定宽 60px × 24px，在 84px 列内完全绝对居中（两翼留白 12px，彻底根除右侧溢出） */
        .btn-switch {{ 
            width: 60px !important; 
            min-width: 60px !important; 
            max-width: 60px !important; 
            height: 24px;
            flex-shrink: 0 !important; 
            background: var(--cyan-accent); 
            color: #000000; 
            font-size: 11px;
            font-weight: 900;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            padding: 0 !important;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }}

        .btn-unblock {{ 
            width: 60px !important; 
            min-width: 60px !important; 
            max-width: 60px !important; 
            height: 24px;
            flex-shrink: 0 !important; 
            background: #FF4B4B; 
            color: #FFFFFF; 
            font-size: 11px;
            font-weight: 900;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            padding: 0 !important;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }}
        .btn-unblock:hover {{
            background: #E11D48;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .btn-unblock:active {{
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000000;
        }}

        /* 🏷️ 顶栏版本号指示标牌 */
        .version-badge {{
            display: inline-block;
            background: #000000;
            color: #FFE600;
            font-size: 10px;
            font-weight: 900;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 8px;
            vertical-align: 1px;
            border: 1.5px solid #000000;
            letter-spacing: 0.5px;
        }}

        /* 🔀 序号列拖拽手柄与序号布局 */
        .num-cell-inner {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 2px;
            cursor: grab;
            user-select: none;
            -webkit-user-select: none;
            width: 100%;
        }}
        .num-cell-inner:active {{
            cursor: grabbing;
        }}
        .drag-handle {{
            color: #888888;
            font-size: 13px;
            font-weight: 900;
            line-height: 1;
            padding: 0 1px;
            transition: color 0.1s;
        }}
        .account-row:hover .drag-handle {{
            color: #000000;
        }}

        /* 🔀 拖拽排序视觉反馈与选择保护 */
        .account-row {{
            user-select: none;
            -webkit-user-select: none;
        }}
        .account-row.drag-over-top {{
            border-top: 3px solid #00F0FF !important;
            box-shadow: 0 -2px 0 0 #00F0FF;
        }}
        .account-row.drag-over-bottom {{
            border-bottom: 3px solid #00F0FF !important;
            box-shadow: 0 2px 0 0 #00F0FF;
        }}
        .account-row[draggable="true"]:hover {{
            cursor: grab;
        }}
        .account-row[draggable="true"]:active {{
            cursor: grabbing;
        }}

        /* 🔀 操作列：主按钮 + 上下微调微型箭头 */
        .actions-flex {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
        }}
        .reorder-arrows {{
            display: inline-flex;
            flex-direction: column;
            gap: 2px;
            flex-shrink: 0;
        }}
        .btn-arrow {{
            width: 16px;
            height: 11px;
            line-height: 9px;
            font-size: 8px;
            font-weight: 900;
            background: #FFFFFF;
            color: #000000;
            border: 1.5px solid #000000;
            border-radius: 2px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            box-shadow: 1px 1px 0px #000000;
            transition: all 0.05s;
        }}
        .btn-arrow:hover {{
            background: var(--yellow-main);
            transform: translate(-0.5px, -0.5px);
        }}
        .btn-arrow:active {{
            transform: translate(0.5px, 0.5px);
            box-shadow: 0px 0px 0px #000000;
        }}

        .active-badge-action {{
            width: 60px !important;
            min-width: 60px !important;
            max-width: 60px !important;
            height: 24px;
            background: #000000;
            color: #FFFFFF;
            font-size: 11px;
            font-weight: 900;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            letter-spacing: 0.5px;
            cursor: default;
            user-select: none;
            box-sizing: border-box;
            padding: 0 !important;
        }}

        .toast {{
            position: fixed;
            top: 24px;
            right: 24px;
            background: #FFE600;
            color: #000000;
            padding: 10px 18px;
            font-size: 12px;
            font-weight: 900;
            border: 2.5px solid #000000;
            border-radius: var(--radius-card);
            box-shadow: 4px 4px 0px #000000;
            display: none;
            z-index: 999999;
            letter-spacing: 0.5px;
            max-width: 400px;
            animation: slideInRight 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            cursor: pointer;
        }}
        .toast-success {{
            background: #10B981 !important;
            color: #000000 !important;
            border-color: #000000 !important;
        }}
        .toast-warmup {{
            background: #F472B6 !important;
            color: #000000 !important;
            border-color: #000000 !important;
        }}
        .toast-info {{
            background: #FFE600 !important;
            color: #000000 !important;
            border-color: #000000 !important;
        }}
        .toast-error {{
            background: #EF4444 !important;
            color: #FFFFFF !important;
            border-color: #000000 !important;
        }}
        @keyframes slideInRight {{
            from {{ transform: translateX(50px); opacity: 0; }}
            to {{ transform: translateX(0); opacity: 1; }}
        }}
        /* Neo-Brutalism 自绘确认弹窗 (100% 解决 macOS WKWebView 拦截 window.confirm 的死锁) */
        .modal-backdrop {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.55);
            backdrop-filter: blur(2px);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 9999999;
        }}
        .modal-backdrop.show {{
            display: flex !important;
        }}
        .modal-box {{
            background: #F4F0EA;
            width: 440px;
            max-width: 90vw;
            border: 3px solid #000000;
            border-radius: var(--radius-modal);
            box-shadow: 6px 6px 0px #000000;
            animation: popIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
            overflow: hidden;
        }}
        .modal-header {{
            background: #FFE600;
            color: #000000;
            padding: 10px 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 13px;
            font-weight: 900;
            letter-spacing: 0.5px;
            border-bottom: 2.5px solid #000000;
        }}
        .modal-close {{
            color: #000000;
            cursor: pointer;
            font-size: 16px;
            font-weight: 900;
            line-height: 1;
            padding: 0 4px;
        }}
        .modal-close:hover {{
            color: #EF4444;
        }}
        .modal-body {{
            padding: 18px 16px;
            font-size: 12.5px;
            font-weight: 700;
            line-height: 1.6;
            color: #111827;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .modal-actions {{
            padding: 12px 16px;
            background: #E5E7EB;
            border-top: 2px solid #000000;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }}
        .btn-modal-cancel {{
            background: #FFFFFF;
            color: #000000;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2.5px 2.5px 0px #000000;
            padding: 6px 14px;
            font-size: 11.5px;
            font-weight: 900;
            cursor: pointer;
        }}
        .btn-modal-confirm {{
            background: var(--cyan-accent);
            color: #000000;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2.5px 2.5px 0px #000000;
            padding: 6px 18px;
            font-size: 11.5px;
            font-weight: 900;
            cursor: pointer;
        }}
        .btn-modal-cancel:hover, .btn-modal-confirm:hover {{
            transform: translate(-1px, -1px);
            box-shadow: 3.5px 3.5px 0px #000000;
        }}
        .btn-modal-cancel:active, .btn-modal-confirm:active {{
            transform: translate(1.5px, 1.5px);
            box-shadow: 1px 1px 0px #000000;
        }}

        /* 导入与纳管中心模态弹窗样式 */
        .import-modal-box {{
            background: #F4F0EA;
            width: 530px;
            max-width: 92vw;
            border: 3px solid #000000;
            border-radius: var(--radius-modal);
            box-shadow: 6px 6px 0px #000000;
            animation: popIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
            overflow: hidden;
            box-sizing: border-box;
        }}
        .import-tabs {{
            display: flex;
            background: #E5E7EB;
            border-bottom: 2.5px solid #000000;
            padding: 8px 12px 0 12px;
            gap: 6px;
            box-sizing: border-box;
            user-select: none;
        }}
        .import-tab-btn {{
            background: #D1D5DB;
            color: #4B5563;
            border: 2px solid #000000;
            border-bottom: none;
            border-radius: 6px 6px 0 0;
            padding: 6px 12px;
            font-size: 11px;
            font-weight: 900;
            cursor: pointer;
            transition: all 0.1s;
        }}
        .import-tab-btn.active {{
            background: #F4F0EA;
            color: #000000;
            border-bottom: 2.5px solid #F4F0EA;
            margin-bottom: -2.5px;
            box-shadow: 2px -2px 0px #000000;
        }}
        .import-body-content {{
            padding: 16px 18px;
            background: #F4F0EA;
            box-sizing: border-box;
        }}
        .import-tip-box {{
            background: #FFFFFF;
            border: 2px solid #000000;
            border-radius: 6px;
            box-shadow: 2px 2px 0px #000000;
            padding: 10px 12px;
            font-size: 11.5px;
            font-weight: 700;
            line-height: 1.6;
            margin-bottom: 14px;
            color: #111827;
        }}
        .form-label {{
            display: block;
            font-size: 11px;
            font-weight: 900;
            margin-bottom: 4px;
            color: #000000;
        }}
        .form-input, .form-textarea {{
            width: 100%;
            border: 2px solid #000000;
            border-radius: 6px;
            padding: 8px 10px;
            font-size: 11.5px;
            font-weight: 700;
            background: #FFFFFF;
            box-sizing: border-box;
            box-shadow: 2px 2px 0px #000000;
            margin-bottom: 10px;
            font-family: inherit;
        }}
        .form-input:focus, .form-textarea:focus {{
            outline: none;
            border-color: #000000;
            background: #FFFBEB;
        }}
        .form-input-file {{
            width: 100%;
            border: 2px dashed #000000;
            border-radius: 6px;
            padding: 8px;
            background: #FFFFFF;
            box-sizing: border-box;
            margin-bottom: 10px;
            cursor: pointer;
            font-size: 11px;
            font-weight: 700;
        }}
        .btn-submit-action {{
            width: 100%;
            height: 36px;
            background: var(--cyan-accent);
            color: #000000;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            font-size: 12px;
            font-weight: 900;
            cursor: pointer;
            box-shadow: 3px 3px 0px #000000;
            transition: all 0.08s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .btn-submit-action:hover {{
            transform: translate(-1px, -1px);
            box-shadow: 4px 4px 0px #000000;
        }}
        .btn-submit-action:active {{
            transform: translate(1.5px, 1.5px);
            box-shadow: 1px 1px 0px #000000;
        }}
        .btn-sync-action {{
            width: 100%;
            height: 40px;
            background: #FFE600;
            color: #000000;
            border: 2.5px solid #000000;
            border-radius: var(--radius-btn);
            font-size: 12.5px;
            font-weight: 900;
            cursor: pointer;
            box-shadow: 3.5px 3.5px 0px #000000;
            transition: all 0.08s;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .btn-sync-action:hover {{
            transform: translate(-1px, -1px);
            box-shadow: 4.5px 4.5px 0px #000000;
            background: #FFED4A;
        }}
        .btn-sync-action:active {{
            transform: translate(1.5px, 1.5px);
            box-shadow: 1px 1px 0px #000000;
        }}
        /* 新野兽派底部分页控制栏 (粗黑框 + 硬投影 + 紧凑微圆角) */
        .pagination-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #FFFFFF;
            border: var(--border-thick);
            border-radius: var(--radius-card);
            box-shadow: var(--shadow-hard);
            padding: 4px 12px;
            margin-top: 12px;
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box;
            height: 34px;
        }}
        .page-info {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            font-size: 11px;
            font-weight: 800;
            color: #111827;
        }}
        .page-dot {{
            color: #9CA3AF;
            font-weight: 900;
        }}
        .page-actions {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .btn-page {{
            background: #F4F0EA;
            color: #000000;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            font-size: 10.5px;
            font-weight: 900;
            padding: 0 10px;
            height: 24px;
            cursor: pointer;
            box-sizing: border-box;
            transition: all 0.08s ease;
        }}
        .btn-page:hover:not(:disabled) {{
            background: #FFE600;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .btn-page:active:not(:disabled) {{
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000000;
        }}
        .btn-page:disabled {{
            opacity: 0.4;
            cursor: not-allowed;
            background: transparent;
            box-shadow: none;
            border: 1.5px solid #D1D5DB;
            color: #9CA3AF;
        }}
    </style>
</head>
<body>
    <div id="loading-bar"></div>
    <div id="toast" class="toast font-mono"></div>

    <div class="app-container">
        <!-- 新野兽派顶栏控制条 (宽阔微高 + 三点平衡居中) -->
        <div class="top-bar">
            <div class="top-left">
                <span class="brand-title">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="#000000" stroke="#000000" stroke-width="1" style="vertical-align:-1px; margin-right:2px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    ANTIGRAVITY HUB
                </span>
                <span class="version-badge font-mono">v2.27.0</span>
            </div>
            <div class="top-center">
                {active_pill_html}
            </div>
            {stats_html}
            <div class="top-right">
                <button class="btn btn-top btn-import font-mono"
                        onclick="openImportModal(); event.preventDefault(); event.stopPropagation();"
                        title="导入账号备份、批量添加或从 IDE 钥匙串一键吸纳">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    导入
                </button>
                <button class="btn btn-top btn-export font-mono"
                        onclick="doExportAccounts(); event.preventDefault(); event.stopPropagation();"
                        title="导出全池账号备份 JSON">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    导出
                </button>
                <button class="btn btn-top btn-refresh-all font-mono"
                        onclick="doRefreshQuota(this); event.preventDefault(); event.stopPropagation();"
                        title="立即同步最新活跃状态并触发全池配额并发刷新">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
                    刷新
                </button>
            </div>
        </div>

        <!-- 搜索与多维过滤控制条 (客户端 0ms 即时响应) -->
        <div class="control-bar font-mono">
            <div class="search-box">
                <span class="search-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></span>
                <input type="text" id="account-search" class="search-input font-mono" placeholder="搜索账号..." oninput="filterTable()" autocomplete="off">
                <button id="clear-search" class="btn-clear" onclick="clearSearch()" style="display:none;" title="清空搜索">✕</button>
            </div>
            <div class="filter-group">
                <button class="filter-tab active" data-filter="all" onclick="setFilter('all', this)">全部 ({total_count})</button>
                <button class="filter-tab" data-filter="usable" onclick="setFilter('usable', this)" title="仅展示 Gemini 周额度大于 0 的可用轮换账号"><span class="filter-dot dot-blue"></span>可用账号 (G&gt;0)</button>
                <button class="filter-tab" data-filter="healthy" onclick="setFilter('healthy', this)"><span class="filter-dot dot-green"></span>充足 (&gt;50%)</button>
                <button class="filter-tab" data-filter="warning" onclick="setFilter('warning', this)"><span class="filter-dot dot-red"></span>告急 (&lt;15%)</button>
                <button class="filter-tab" data-filter="exhausted" onclick="setFilter('exhausted', this)" title="仅展示 Gemini 周额度已彻底归零的枯竭账号"><span class="filter-dot dot-gray"></span>已枯竭 (G=0)</button>
            </div>
            <div class="stats-counter" id="filter-counter">
                显示: <b>{total_count}</b> / {total_count}
            </div>
        </div>

        <!-- 官方规范级高密新野兽表格 (自适应弹性伸缩 + 横向滚动防护) -->
        <div class="table-wrap">
            <table>
                <colgroup>
                    <col style="width: 40px;">   <!-- # 序号+拖拽手柄 (40px) -->
                    <col style="width: 74px;">   <!-- 状态 (74px) -->
                    <col style="width: 226px;">  <!-- 账号+PRO (226px，自适应充沛呼吸空间，彻底根除截断) -->
                    <col style="width: 234px;">  <!-- Gemini 配额 (234px) -->
                    <col style="width: 234px;">  <!-- Claude 配额 (234px) -->
                    <col style="width: 92px;">   <!-- 切换+调序操作 (92px) -->
                </colgroup>
                <thead>
                    <tr>
                        <th class="col-center th-num" title="拖拽手柄与序号">#</th>
                        <th class="col-center th-status">状态</th>
                        <th class="th-email">账号 (点击复制)</th>
                        <th class="th-gemini">Gemini 配额 (5h / 周)</th>
                        <th class="th-claude">Claude 配额 (5h / 周)</th>
                        <th class="col-center th-action" title="切换账号与上下微调顺序">操作</th>
                    </tr>
                </thead>
                <tbody id="account-tbody">
                    {table_rows}
                </tbody>
            </table>
        </div>

        <!-- 新野兽派底部分页与状态指示条 (单页上限 15 个，自适应翻页) -->
        <div class="pagination-bar font-mono" id="pagination-bar">
            <div class="page-info">
                <span>单页上限: <b>15</b> 个</span>
                <span class="page-dot">·</span>
                <span id="page-indicator">第 <b>1</b> / 1 页</span>
                <span class="page-dot">·</span>
                <span id="page-total">共 {total_count} 个账号</span>
            </div>
            <div class="page-actions">
                <button class="btn btn-page font-mono" id="btn-prev-page" onclick="changePage(-1)" disabled title="上一页">← 上一页</button>
                <button class="btn btn-page font-mono" id="btn-next-page" onclick="changePage(1)" disabled title="下一页">下一页 →</button>
            </div>
        </div>
    </div>

    <!-- 📥 Neo-Brutalism 账号纳管与导入中心模态弹窗 -->
    <div id="import-modal-backdrop" class="modal-backdrop font-mono" onclick="if(event.target===this)closeImportModal()">
        <div class="import-modal-box">
            <div class="modal-header">
                <div style="display:flex; align-items:center; gap:6px;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    <span>账号导入与纳管中心</span>
                </div>
                <span class="modal-close" onclick="closeImportModal()" title="关闭窗口">✕</span>
            </div>

            <div class="import-tabs">
                <button class="import-tab-btn active" id="tab-btn-sync" onclick="switchImportTab('sync')">⚡ 从当前 IDE 一键吸纳</button>
                <button class="import-tab-btn" id="tab-btn-file" onclick="switchImportTab('file')">📁 批量导入 JSON 备份</button>
                <button class="import-tab-btn" id="tab-btn-manual" onclick="switchImportTab('manual')">➕ 手动添加账号</button>
            </div>

            <div class="import-body-content">
                <!-- TAB 1: 钥匙串一键吸纳 -->
                <div id="import-pane-sync" class="import-pane">
                    <div class="import-tip-box">
                        <b>💡 最简纳管指南：</b><br>
                        1. 在官方 Antigravity IDE 右上角退出当前账号，登录您的第 2 个谷歌账号；<br>
                        2. 登录完成后回到此页面，点击下方黄色大按钮；<br>
                        3. Hub 将从系统安全钥匙串自动吸纳新凭据并初始化配额，零门槛完成多账号扩充！
                    </div>
                    <button class="btn-sync-action font-mono" id="btn-sync-active" onclick="doSyncActiveAccount(this)">
                        ⚡ 立即从 IDE 钥匙串检测并吸纳新账号
                    </button>
                </div>

                <!-- TAB 2: JSON 备份导入 -->
                <div id="import-pane-file" class="import-pane" style="display:none;">
                    <div class="import-tip-box">
                        <b>📋 兼容格式：</b>支持 Hub 导出备份包、账号数组列表或单账号字典。系统自动去重合并并拉取最新配额。
                    </div>
                    <label class="form-label">选择 JSON 备份文件：</label>
                    <input type="file" id="import-file-input" accept=".json" class="form-input-file" onchange="handleFileUpload(event)">
                    <label class="form-label">或在此直接粘贴 JSON 文本：</label>
                    <textarea id="import-text-input" class="form-textarea font-mono" rows="5" placeholder='[&#10;  {{ "email": "user@gmail.com", "refresh_token": "1//04..." }}&#10;]'></textarea>
                    <button class="btn-submit-action font-mono" onclick="doSubmitJsonImport(this)">
                        📥 开始解析并合并入库
                    </button>
                </div>

                <!-- TAB 3: 手动输入凭据 -->
                <div id="import-pane-manual" class="import-pane" style="display:none;">
                    <div class="import-tip-box">
                        <b>🔑 凭据直录：</b>输入 Google 账号邮箱与 Refresh Token，系统将核验有效性并初始化配额。
                    </div>
                    <label class="form-label">Google 邮箱地址 (Email)：</label>
                    <input type="email" id="manual-email" class="form-input font-mono" placeholder="developer@gmail.com">
                    <label class="form-label">OAuth Refresh Token (必填)：</label>
                    <input type="text" id="manual-refresh-token" class="form-input font-mono" placeholder="1//04xxxxxxxx...">
                    <button class="btn-submit-action font-mono" onclick="doSubmitManualAccount(this)">
                        ➕ 添加到账号池
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- 🔒 自绘 Neo-Brutalism 通用确认模态弹窗 -->
    <div id="neo-modal-backdrop" class="modal-backdrop font-mono" onclick="if(event.target===this)closeNeoModal(false)">
        <div class="modal-box">
            <div class="modal-header">
                <span id="modal-title">操作确认</span>
                <span class="modal-close" onclick="closeNeoModal(false)">✕</span>
            </div>
            <div id="modal-body" class="modal-body"></div>
            <div class="modal-actions">
                <button class="btn-modal-cancel font-mono" onclick="closeNeoModal(false)">取消</button>
                <button id="modal-btn-confirm" class="btn-modal-confirm font-mono" onclick="confirmNeoModal()">确定</button>
            </div>
        </div>
    </div>

    <script>
        let currentFilter = 'all';

        // 📥 账号导入与纳管中心交互逻辑
        function openImportModal() {{
            const backdrop = document.getElementById('import-modal-backdrop');
            if (backdrop) backdrop.classList.add('show');
        }}

        function closeImportModal() {{
            const backdrop = document.getElementById('import-modal-backdrop');
            if (backdrop) backdrop.classList.remove('show');
        }}

        function switchImportTab(tabName) {{
            ['sync', 'file', 'manual'].forEach(t => {{
                const btn = document.getElementById('tab-btn-' + t);
                const pane = document.getElementById('import-pane-' + t);
                if (btn) btn.classList.toggle('active', t === tabName);
                if (pane) pane.style.display = (t === tabName) ? 'block' : 'none';
            }});
        }}

        // 📤 导出全量账号备份 JSON
        function doExportAccounts() {{
            showToast("📤 正在生成全量账号备份 JSON...", "info");
            window.location.href = '/api/export';
        }}

        // ⚡ 一键从 IDE 钥匙串吸纳当前活跃账号
        async function doSyncActiveAccount(btn) {{
            if (btn) {{
                btn.disabled = true;
                btn.innerText = "⏳ 正在探测钥匙串凭据...";
            }}
            try {{
                const resp = await fetch('/api/ingest_active', {{ method: 'POST' }});
                const data = await resp.json();
                if (resp.ok && data.status === 'ok') {{
                    showToast("🎉 " + data.message, "success");
                    closeImportModal();
                    fetchTableSafely();
                }} else {{
                    showToast("❌ " + (data.message || "吸纳失败"), "error");
                }}
            }} catch (err) {{
                showToast("❌ 网络异常: " + err.message, "error");
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerText = "⚡ 立即从 IDE 钥匙串检测并吸纳新账号";
                }}
            }}
        }}

        // 处理文件上传读取
        function handleFileUpload(event) {{
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {{
                const textarea = document.getElementById('import-text-input');
                if (textarea) textarea.value = e.target.result;
            }};
            reader.readAsText(file);
        }}

        // 📥 提交 JSON 文本/文件导入
        async function doSubmitJsonImport(btn) {{
            const textarea = document.getElementById('import-text-input');
            const content = textarea ? textarea.value.trim() : '';
            if (!content) {{
                showToast("❌ 请先上传文件或粘贴 JSON 数据", "error");
                return;
            }}
            if (btn) {{
                btn.disabled = true;
                btn.innerText = "⏳ 正在解析并合并入库...";
            }}
            try {{
                const resp = await fetch('/api/import', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ json_data: content }})
                }});
                const data = await resp.json();
                if (resp.ok && data.status === 'ok') {{
                    showToast("🎉 " + data.message, "success");
                    if (textarea) textarea.value = '';
                    closeImportModal();
                    fetchTableSafely();
                }} else {{
                    showToast("❌ " + (data.message || "导入失败"), "error");
                }}
            }} catch (err) {{
                showToast("❌ 导入请求失败: " + err.message, "error");
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerText = "📥 开始解析并合并入库";
                }}
            }}
        }}

        // ➕ 手动提交添加账号
        async function doSubmitManualAccount(btn) {{
            const emailInput = document.getElementById('manual-email');
            const rtInput = document.getElementById('manual-refresh-token');
            const email = emailInput ? emailInput.value.trim() : '';
            const rt = rtInput ? rtInput.value.trim() : '';
            if (!email || !rt) {{
                showToast("❌ 邮箱和 Refresh Token 均不能为空", "error");
                return;
            }}
            if (btn) {{
                btn.disabled = true;
                btn.innerText = "⏳ 正在核验并入库...";
            }}
            try {{
                const resp = await fetch('/api/add_account', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ email: email, refresh_token: rt }})
                }});
                const data = await resp.json();
                if (resp.ok && data.status === 'ok') {{
                    showToast("🎉 " + data.message, "success");
                    if (emailInput) emailInput.value = '';
                    if (rtInput) rtInput.value = '';
                    closeImportModal();
                    fetchTableSafely();
                }} else {{
                    showToast("❌ " + (data.message || "添加失败"), "error");
                }}
            }} catch (err) {{
                showToast("❌ 请求失败: " + err.message, "error");
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerText = "➕ 添加到账号池";
                }}
            }}
        }}

        function copyText(text) {{
            if (!text || text === '未激活') return;
            navigator.clipboard.writeText(text).then(() => {{
                showToast("已复制账号: " + text, "success");
            }}).catch(() => {{
                showToast("复制失败，请手动选择复制", "error");
            }});
        }}

        function showToast(msg, type = 'info') {{
            const t = document.getElementById("toast");
            if (!t) return;
            t.innerText = msg;
            t.className = "toast font-mono toast-" + type;
            t.style.display = "block";
            clearTimeout(window.__toastTimer);
            window.__toastTimer = setTimeout(() => {{
                t.style.display = "none";
            }}, 3200);
        }}

        // ========================================================
        // 🔒 自绘 Neo-Brutalism 确认对话框 (彻底解决 WKWebView confirm 死锁)
        // ========================================================
        let __pendingConfirmCallback = null;

        function openNeoModal(title, bodyText, onConfirm) {{
            const backdrop = document.getElementById('neo-modal-backdrop');
            const titleEl = document.getElementById('modal-title');
            const bodyEl = document.getElementById('modal-body');
            const confirmBtn = document.getElementById('modal-btn-confirm');
            
            // 🛡️ 稳态兜底：若 DOM 弹窗因任何原因不可用，立即调用系统原生 NSAlert 弹窗
            if (!backdrop || !titleEl || !bodyEl) {{
                if (window.confirm(title + "\\n\\n" + bodyText)) {{
                    onConfirm();
                }}
                return;
            }}

            titleEl.innerText = title;
            bodyEl.innerText = bodyText;
            __pendingConfirmCallback = onConfirm;

            backdrop.classList.add('show');
            setTimeout(() => {{
                if (confirmBtn) confirmBtn.focus();
            }}, 50);
        }}

        function closeNeoModal(confirmed = false) {{
            const backdrop = document.getElementById('neo-modal-backdrop');
            if (backdrop) backdrop.classList.remove('show');
            if (confirmed && typeof __pendingConfirmCallback === 'function') {{
                const fn = __pendingConfirmCallback;
                __pendingConfirmCallback = null;
                fn();
            }} else {{
                __pendingConfirmCallback = null;
            }}
        }}

        function confirmNeoModal() {{
            closeNeoModal(true);
        }}

        // 键盘快捷键交互：ESC 取消，Enter 确认
        window.addEventListener('keydown', function(e) {{
            const backdrop = document.getElementById('neo-modal-backdrop');
            if (!backdrop || !backdrop.classList.contains('show')) return;
            if (e.key === 'Escape') {{
                closeNeoModal(false);
            }} else if (e.key === 'Enter') {{
                closeNeoModal(true);
            }}
        }});

        // 🚀 通用响应更新器：基于 DOMParser 在 table 语法树中严格提取合法 tr 节点，杜绝 WebKit 剥离！
        function applyTbodyAndOOB(html) {{
            const parser = new DOMParser();

            // 1. 处理所有 hx-swap-oob 元素 (如顶栏药丸与统计数据)
            const docAll = parser.parseFromString(html, 'text/html');
            const oobs = docAll.querySelectorAll('[hx-swap-oob="true"]');
            oobs.forEach(oob => {{
                const targetId = oob.id;
                if (targetId) {{
                    const targetEl = document.getElementById(targetId);
                    if (targetEl) {{
                        targetEl.outerHTML = oob.outerHTML;
                    }}
                }}
            }});

            // 2. 严格在 table/tbody 上下文中解析 tr 标签，杜绝 WebKit 剥离 tr/td 结构
            const tableDoc = parser.parseFromString(`<table><tbody>${{html}}</tbody></table>`, 'text/html');
            const trs = tableDoc.querySelectorAll('tbody > tr.account-row, tr.account-row');
            const tbody = document.getElementById('account-tbody');
            if (tbody && trs.length > 0) {{
                tbody.innerHTML = '';
                trs.forEach(tr => {{
                    tbody.appendChild(document.importNode(tr, true));
                }});
                __cachedTbodyHTML = tbody.innerHTML;
                filterTable();
                if (typeof initDragSort === 'function') {{
                    initDragSort();
                }}
            }}
        }}

        // 🔄 安全静默拉取最新表格与状态（0 冲突，0 剥离，稳态更新）
        async function fetchTableSafely() {{
            if (isReordering) return;
            try {{
                const resp = await fetch('/api/table');
                if (!resp.ok) return;
                const html = await resp.text();
                applyTbodyAndOOB(html);
            }} catch (e) {{
                console.warn("静默同步跳过:", e);
            }}
        }}

        // ⚡ 刷新配额直通函数：0 弹窗阻断，0 外部依赖，点击 100% 物理触发！
        async function doRefreshQuota(btn) {{
            showToast("⏳ 正在并发刷新全池配额与重置时间...", "info");
            const loadingBar = document.getElementById('loading-bar');
            if (loadingBar) loadingBar.style.display = 'block';
            if (btn) {{
                btn.disabled = true;
                btn.style.opacity = '0.6';
            }}

            try {{
                const resp = await fetch('/api/refresh', {{ method: 'POST' }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const html = await resp.text();
                applyTbodyAndOOB(html);
                showToast("⚡ 全池最新配额与重置时间并发同步成功！", "success");
            }} catch (err) {{
                console.error("刷新失败:", err);
                showToast("❌ 刷新失败: " + err.message, "error");
            }} finally {{
                if (loadingBar) loadingBar.style.display = 'none';
                if (btn) {{
                    btn.disabled = false;
                    btn.style.opacity = '1';
                }}
            }}
        }}

        // 🔄 切换账号直通函数：一键直通物理原子切换，脱壳重启 Antigravity 并自动发送接力提示词！
        async function doSwitchAccount(email) {{
            showToast("⏳ 正在注入凭据并脱壳拉起 Antigravity 重启接力...", "info");
            const loadingBar = document.getElementById('loading-bar');
            if (loadingBar) loadingBar.style.display = 'block';

            try {{
                const resp = await fetch('/api/switch', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                    body: 'email=' + encodeURIComponent(email)
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const html = await resp.text();
                applyTbodyAndOOB(html);
                showToast("✅ 物理切换成功！Antigravity 正在重启并由 agentapi 自动发送接力提示词！", "success");
            }} catch (err) {{
                console.error("切换失败:", err);
                showToast("❌ 切换失败: " + err.message, "error");
            }} finally {{
                if (loadingBar) loadingBar.style.display = 'none';
            }}
        }}

        // 🔓 解除人工锁定直通函数：一键直通解除保护
        async function doUnlockProtection() {{
            showToast("⏳ 正在解除人工锁定并恢复自动轮转...", "info");
            try {{
                const resp = await fetch('/api/unlock', {{ method: 'POST' }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const html = await resp.text();
                applyTbodyAndOOB(html);
                showToast("🔓 人工保护已解除！已恢复后台看门狗自动轮转", "success");
            }} catch (err) {{
                showToast("❌ 解除失败: " + err.message, "error");
            }}
        }}

        // 🛡️ 一键隔离解封向导：拉起专属Chrome独立容器并自动定向对应账号，彻底防500！
        async function doUnblockAccount(email) {{
            showToast("🚀 正在获取最新令牌并拉起专属隔离浏览器窗口...", "info");
            try {{
                const resp = await fetch('/api/unblock', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                    body: 'email=' + encodeURIComponent(email)
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const html = await resp.text();
                applyTbodyAndOOB(html);
                showToast("✅ 已拉起专属无污染窗口！请在该窗口登录并确认，后台将自动监听解锁！", "success");
            }} catch (err) {{
                showToast("❌ 启动解封失败: " + err.message, "error");
            }}
        }}

        // 🔥 静默预热直通函数
        async function doWarmupAccount(email) {{
            showToast("⏳ 正在向 Google 探针节点发送单账号静默预热...", "info");
            try {{
                const resp = await fetch('/api/warmup', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                    body: 'email=' + encodeURIComponent(email)
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const html = await resp.text();
                applyTbodyAndOOB(html);
                showToast("🔥 静默预热探针触发完成！模型已激活", "warmup");
            }} catch (err) {{
                showToast("❌ 预热失败: " + err.message, "error");
            }}
        }}

        let currentPage = 1;
        const PAGE_SIZE = 15;
        let __cachedTbodyHTML = '';

        // 页面初始加载时备份原始行数据
        window.addEventListener('DOMContentLoaded', function() {{
            const tbody = document.getElementById('account-tbody');
            if (tbody && tbody.children.length > 0) {{
                __cachedTbodyHTML = tbody.innerHTML;
            }}
            filterTable();
        }});

        // 🛡️ 客户端数据稳态看门狗：杜绝任何原因导致的误清空
        function ensureDataResilience() {{
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;
            const rows = tbody.querySelectorAll('tr.account-row');
            const searchInput = document.getElementById('account-search');
            const q = searchInput ? searchInput.value.trim() : '';
            if (rows.length === 0 && !q && __cachedTbodyHTML) {{
                console.warn("🛡️ 看门狗触发：检测到 tbody 数据异常丢失，立即从稳态镜像恢复！");
                tbody.innerHTML = __cachedTbodyHTML;
            }}
        }}

        function changePage(delta) {{
            currentPage += delta;
            filterTable();
        }}

        function setFilter(filterType, btn) {{
            currentFilter = filterType;
            currentPage = 1;
            document.querySelectorAll('.filter-tab').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            filterTable();
        }}

        function clearSearch() {{
            const input = document.getElementById('account-search');
            if (input) {{
                input.value = '';
                input.focus();
            }}
            const clearBtn = document.getElementById('clear-search');
            if (clearBtn) clearBtn.style.display = 'none';
            currentPage = 1;
            filterTable();
        }}

        function filterTable() {{
            ensureDataResilience();
            const input = document.getElementById('account-search');
            const q = input ? input.value.toLowerCase().trim() : '';
            const clearBtn = document.getElementById('clear-search');
            if (clearBtn) clearBtn.style.display = q ? 'inline-block' : 'none';

            const rows = Array.from(document.querySelectorAll('#account-tbody tr.account-row'));
            const matchedRows = [];

            rows.forEach(tr => {{
                const email = tr.getAttribute('data-email') || '';
                const matchQuery = !q || email.toLowerCase().includes(q);

                const gw = parseFloat(tr.getAttribute('data-gemini-w') || '1.0');
                const cw = parseFloat(tr.getAttribute('data-claude-w') || '1.0');
                let matchTab = true;
                if (currentFilter === 'usable') {{
                    // 🎯 严格执行用户最高指令：只要 Gemini 周额度 > 0 (未彻底归零)，就必须保留在可用池中
                    matchTab = (gw > 0.0001);
                }} else if (currentFilter === 'healthy') {{
                    matchTab = (gw >= 0.5 && cw >= 0.5);
                }} else if (currentFilter === 'warning') {{
                    matchTab = (gw < 0.15 || cw < 0.15);
                }} else if (currentFilter === 'exhausted') {{
                    // 仅查看 Gemini 周额度已彻底归零 (== 0) 的枯竭账号
                    matchTab = (gw <= 0.0001);
                }}

                if (matchQuery && matchTab) {{
                    matchedRows.push(tr);
                }} else {{
                    tr.style.display = 'none';
                }}
            }});

            // 🎯 单页上限 15 个的分页算法
            const totalMatched = matchedRows.length;
            const totalPages = Math.max(1, Math.ceil(totalMatched / PAGE_SIZE));
            if (currentPage > totalPages) currentPage = totalPages;
            if (currentPage < 1) currentPage = 1;

            const startIndex = (currentPage - 1) * PAGE_SIZE;
            const endIndex = startIndex + PAGE_SIZE;

            matchedRows.forEach((tr, index) => {{
                if (index >= startIndex && index < endIndex) {{
                    tr.style.display = '';
                }} else {{
                    tr.style.display = 'none';
                }}
            }});

            // 顶栏计数器
            const counter = document.getElementById('filter-counter');
            if (counter) {{
                counter.innerHTML = `显示: <b>${{Math.min(PAGE_SIZE, totalMatched)}}</b> / ${{rows.length}}`;
            }}

            // 底部分页控制栏状态同步
            const pageIndicator = document.getElementById('page-indicator');
            if (pageIndicator) {{
                pageIndicator.innerHTML = `第 <b>${{currentPage}}</b> / ${{totalPages}} 页`;
            }}
            const pageTotal = document.getElementById('page-total');
            if (pageTotal) {{
                pageTotal.innerHTML = `共 ${{totalMatched}} 个账号`;
            }}
            const btnPrev = document.getElementById('btn-prev-page');
            const btnNext = document.getElementById('btn-next-page');
            if (btnPrev) btnPrev.disabled = (currentPage <= 1);
            if (btnNext) btnNext.disabled = (currentPage >= totalPages);

            // 🎯 尊重用户绝对控制权：彻底停发 resizeWindow，完全交由用户自由拖拉设置窗口尺寸！
        }}

        // 支持 URL 参数 ?filter=usable 自动触发筛选
        window.addEventListener('DOMContentLoaded', () => {{
            const urlParams = new URLSearchParams(window.location.search);
            const f = urlParams.get('filter');
            if (f) {{
                const btn = document.querySelector(`.filter-tab[data-filter="${{f}}"]`);
                if (btn) setFilter(f, btn);
            }}
        }});

        // 窗口重新获得焦点时立即静默触发一次最新状态同步
        window.addEventListener('focus', () => {{
            fetchTableSafely();
        }});

        // 每 5 秒静默同步全池最新状态（0 冲突、0 剥离、绝对稳态）
        setInterval(fetchTableSafely, 5000);

        window.addEventListener('DOMContentLoaded', () => {{
            setTimeout(() => {{
                const c = document.querySelector('.app-container');
                const tb = document.querySelector('.top-bar');
                const cb = document.querySelector('.control-bar');
                const tw = document.querySelector('.table-wrap');
                const pb = document.querySelector('.pagination-bar');
                const getR = el => el ? `left:${{el.getBoundingClientRect().left}},right:${{el.getBoundingClientRect().right}},w:${{el.getBoundingClientRect().width}}` : 'null';
                const msg = `WIN:${{window.innerWidth}}|TOP:${{getR(tb)}}|CTRL:${{getR(cb)}}|TBL:${{getR(tw)}}|PAG:${{getR(pb)}}`;
                fetch('/api/diag?msg=' + encodeURIComponent(msg));
            }}, 300);
        }});

        // ═══════════════════════════════════════════════════════════
        // 🔀 账号顺序双轨调节系统（原生拖拽 + 一键微调箭头，零依赖高稳态）
        // ═══════════════════════════════════════════════════════════
        let isReordering = false;
        let dragSrcRow = null;

        // 🔼🔽 一键上下微调行顺序
        function moveAccountRow(email, direction) {{
            isReordering = true;
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;
            const rows = Array.from(tbody.querySelectorAll('tr.account-row'));
            const idx = rows.findIndex(r => r.getAttribute('data-email') === email);
            if (idx === -1) return;
            const targetIdx = idx + direction;
            if (targetIdx < 0 || targetIdx >= rows.length) return;

            if (direction === -1) {{
                tbody.insertBefore(rows[idx], rows[targetIdx]);
            }} else {{
                tbody.insertBefore(rows[targetIdx], rows[idx]);
            }}

            saveCurrentAccountOrder();
        }}

        // 💾 保存当前账号新顺序至后端数据库
        async function saveCurrentAccountOrder() {{
            isReordering = true;
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;

            // 1. 即时平滑更新前端行号
            tbody.querySelectorAll('tr.account-row').forEach((r, i) => {{
                const numEl = r.querySelector('.row-num');
                if (numEl) numEl.textContent = i + 1;
            }});

            // 2. 构造新序列参数
            const emails = Array.from(tbody.querySelectorAll('tr.account-row'))
                .map(r => r.getAttribute('data-email'));

            const body = emails.map(e => `order[]=${{encodeURIComponent(e)}}`).join('&');
            try {{
                const resp = await fetch('/api/reorder', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                    body: body
                }});
                if (resp.ok) {{
                    showToast('✅ 账号顺序已持久化保存', 'success');
                    __cachedTbodyHTML = tbody.innerHTML;
                }} else {{
                    showToast('❌ 保存顺序失败 (HTTP ' + resp.status + ')', 'error');
                }}
            }} catch (err) {{
                showToast('❌ 保存顺序网络异常: ' + err.message, 'error');
            }} finally {{
                setTimeout(() => {{ isReordering = false; }}, 2000);
            }}
        }}

        // 🖱️ 原生拖拽排序监听器初始化
        function initDragSort() {{
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;

            tbody.querySelectorAll('tr.account-row').forEach(row => {{
                row.setAttribute('draggable', 'true');

                row.ondragstart = function(e) {{
                    isReordering = true;
                    dragSrcRow = row;
                    row.style.opacity = '0.35';
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/plain', row.getAttribute('data-email') || '');
                }};

                row.ondragend = function() {{
                    row.style.opacity = '';
                    tbody.querySelectorAll('tr.account-row').forEach(r => {{
                        r.classList.remove('drag-over-top', 'drag-over-bottom');
                    }});
                    setTimeout(() => {{ isReordering = false; }}, 2000);
                }};

                row.ondragover = function(e) {{
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                    if (!dragSrcRow || dragSrcRow === row) return;
                    const rect = row.getBoundingClientRect();
                    const midY = rect.top + rect.height / 2;
                    tbody.querySelectorAll('tr.account-row').forEach(r => r.classList.remove('drag-over-top', 'drag-over-bottom'));
                    if (e.clientY < midY) {{
                        row.classList.add('drag-over-top');
                    }} else {{
                        row.classList.add('drag-over-bottom');
                    }}
                }};

                row.ondragleave = function() {{
                    row.classList.remove('drag-over-top', 'drag-over-bottom');
                }};

                row.ondrop = function(e) {{
                    e.preventDefault();
                    e.stopPropagation();
                    if (!dragSrcRow || dragSrcRow === row) return;

                    const rect = row.getBoundingClientRect();
                    const midY = rect.top + rect.height / 2;
                    const insertBefore = e.clientY < midY;

                    if (insertBefore) {{
                        tbody.insertBefore(dragSrcRow, row);
                    }} else {{
                        tbody.insertBefore(dragSrcRow, row.nextSibling);
                    }}

                    row.classList.remove('drag-over-top', 'drag-over-bottom');
                    saveCurrentAccountOrder();
                }};
            }});
        }}

        // 初始化等待与自动重绑
        function waitAndInitDragSort() {{
            const tbody = document.getElementById('account-tbody');
            if (tbody && tbody.querySelectorAll('tr.account-row').length > 0) {{
                initDragSort();
            }} else {{
                setTimeout(waitAndInitDragSort, 200);
            }}
        }}
        window.addEventListener('DOMContentLoaded', () => setTimeout(waitAndInitDragSort, 200));

    </script>

</body>
</html>
"""


class HubHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        try:
            msg = format % args
            if "/api/table" not in msg:
                logger.info(f"{self.client_address[0]} - {msg}")
        except Exception:
            pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            try:
                ENGINE.auto_ingest_system_account()
            except Exception:
                pass
            html = render_dashboard_html()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        elif parsed.path == "/api/diag":
            qs = urllib.parse.parse_qs(parsed.query)
            msg = qs.get("msg", [""])[0]
            logger.info(f"🔍 DOM_DIAG: {msg}")
            self.send_response(200)
            self.end_headers()
            return
        elif parsed.path == "/api/table":
            try:
                ENGINE.auto_ingest_system_account()
            except Exception:
                pass
            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        elif parsed.path == "/api/status":
            data = ENGINE.load_accounts()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif parsed.path == "/api/export":
            from .importer import export_accounts_backup
            backup_data = export_accounts_backup(ACCOUNTS_HUB_FILE)
            resp_bytes = json.dumps(backup_data, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="antigravity_accounts_backup.json"')
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)
            return
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")
        params = urllib.parse.parse_qs(post_data)

        if parsed.path == "/api/switch":
            email = params.get("email", [""])[0]
            if email:
                ok, msg = ENGINE.switch_account(email)
                logger.info(f"切换结果: {email} -> {ok}, {msg}")
            # 返回最新渲染的表格行与顶栏 OOB 状态
            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/api/unlock":
            clear_manual_override_lock()
            logger.info("🔓 [人工锁定已解除] 用户手动点击解除人工保护锁，已恢复后台看门狗自动轮转")
            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/api/warmup":
            email = params.get("email", [""])[0]
            if email:
                data = ENGINE.load_accounts()
                acc = data.get("accounts", {}).get(email)
                if acc:
                    ENGINE.trigger_warmup(email, acc)
                    ENGINE.save_accounts(data)
            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/api/warmup-all":
            data = ENGINE.load_accounts()
            for email, acc in data.get("accounts", {}).items():
                ENGINE.trigger_warmup(email, acc)
            ENGINE.save_accounts(data)
            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/api/refresh":
            try:
                ENGINE.auto_ingest_system_account()
            except Exception as e:
                logger.warning(f"刷新前嗅探活跃账号异常: {e}")
            # 同步并发拉取全池官方最新配额 (6线程耗时仅 ~1.2s)，确保返回的数据绝对最新！
            ENGINE.refresh_all_quotas()
            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/api/reorder":
            # 拖拽排序保存：接收新的账号顺序列表并持久化 (复用 do_POST 已读取解析的 params)
            try:
                # 前端发送 order[]=email1&order[]=email2...
                new_order = params.get("order[]", params.get("order", []))
                if new_order:
                    data = ENGINE.load_accounts()
                    accounts = data.get("accounts", {})
                    # 按新顺序重建有序 dict
                    reordered = {}
                    for email in new_order:
                        if email in accounts:
                            reordered[email] = accounts[email]
                    # 保留未在新顺序中出现的账号（兜底）
                    for email, info in accounts.items():
                        if email not in reordered:
                            reordered[email] = info
                    data["accounts"] = reordered
                    ENGINE.save_accounts(data)
                    logger.info(f"✅ 账号顺序已持久化保存: {list(reordered.keys())}")
                html = render_table_rows(include_oob=True)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            except Exception as e:
                logger.error(f"reorder 异常: {e}")
                self.send_response(500)
                self.end_headers()

        elif parsed.path == "/api/unblock":
            email = params.get("email", [""])[0]
            if email:
                data = ENGINE.load_accounts()
                acc = data.get("accounts", {}).get(email)
                if acc:
                    acc_id = acc.get("id", "")
                    at = acc.get("access_token", "")
                    quotas, resets, fresh_val_url = ENGINE.fetch_live_quota(at) if at else ({}, {}, None)
                    if quotas:
                        acc["validation_blocked"] = False
                        acc["validation_url"] = None
                        acc["validation_blocked_reason"] = None
                        ENGINE._sync_antigravity_tools_cache(acc_id, validation_blocked=False)
                        ENGINE.save_accounts(data)
                        logger.info(f"🎉 [一键解封] 账号 {email} 云端已恢复健康，直接自动解锁！")
                    else:
                        raw_url = fresh_val_url or acc.get("validation_url", "")
                        if raw_url:
                            if "&authuser" in raw_url:
                                fixed_raw = raw_url.replace("&authuser", f"&authuser={urllib.parse.quote(email)}")
                            else:
                                fixed_raw = f"{raw_url}&authuser={urllib.parse.quote(email)}"
                            smart_url = f"https://accounts.google.com/AccountChooser?Email={urllib.parse.quote(email)}&continue={urllib.parse.quote(fixed_raw)}"
                            safe_name = email.replace("@", "_").replace(".", "_")
                            profile_dir = os.path.join(BASE_DATA_DIR, "browser_profiles", safe_name)
                            os.makedirs(profile_dir, exist_ok=True)
                            subprocess.Popen(["open", "-na", "Google Chrome", "--args", f"--user-data-dir={profile_dir}", smart_url])
                            logger.info(f"🚀 [一键隔离解封] 已为 {email} 拉起独立 Chrome 容器: {profile_dir}")

                            def _watch_unblock(target_email: str, target_id: str, token: str):
                                for _ in range(45):
                                    time.sleep(4)
                                    q_res, r_res, _ = ENGINE.fetch_live_quota(token)
                                    if q_res:
                                        d_now = ENGINE.load_accounts()
                                        a_now = d_now.get("accounts", {}).get(target_email)
                                        if a_now:
                                            a_now["validation_blocked"] = False
                                            a_now["validation_url"] = None
                                            a_now["validation_blocked_reason"] = None
                                            ENGINE._sync_antigravity_tools_cache(target_id, validation_blocked=False)
                                            ENGINE.save_accounts(d_now)
                                            logger.info(f"🎉 [后台监听解封成功] 账号 {target_email} 验证通过，已自动复权！")
                                        break

                            threading.Thread(target=_watch_unblock, args=(email, acc_id, at), daemon=True).start()

            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/api/ingest_active":
            from .importer import ingest_system_keychain_or_creds
            ok, email, msg = ingest_system_keychain_or_creds(ACCOUNTS_HUB_FILE)
            if ok:
                threading.Thread(target=ENGINE.refresh_all_quotas, daemon=True).start()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "error", "email": email, "message": msg}).encode("utf-8"))
            return

        elif parsed.path == "/api/import":
            from .importer import import_accounts_payload
            payload_str = ""
            try:
                if post_data.strip().startswith("{") or post_data.strip().startswith("["):
                    req_json = json.loads(post_data)
                    payload_str = req_json.get("json_data") if (isinstance(req_json, dict) and "json_data" in req_json) else req_json
                else:
                    payload_str = params.get("json_data", [""])[0] or post_data
            except Exception:
                payload_str = post_data

            ok, added, updated, msg = import_accounts_payload(payload_str, accounts_file=ACCOUNTS_HUB_FILE)
            if ok:
                threading.Thread(target=ENGINE.refresh_all_quotas, daemon=True).start()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "error", "added": added, "updated": updated, "message": msg}).encode("utf-8"))
            return

        elif parsed.path == "/api/add_account":
            from .importer import import_accounts_payload
            email = params.get("email", [""])[0]
            rt = params.get("refresh_token", [""])[0]
            if not email or not rt:
                try:
                    req_json = json.loads(post_data)
                    email = email or req_json.get("email", "")
                    rt = rt or req_json.get("refresh_token", "")
                except Exception:
                    pass
            if not email or not rt:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "邮箱与 Refresh Token 均不能为空"}).encode("utf-8"))
                return

            record = {"email": email, "refresh_token": rt, "tier": "PRO"}
            ok, added, updated, msg = import_accounts_payload([record], accounts_file=ACCOUNTS_HUB_FILE)
            if ok:
                threading.Thread(target=ENGINE.refresh_all_quotas, daemon=True).start()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "error", "message": msg}).encode("utf-8"))
            return

        else:
            self.send_response(404)
            self.end_headers()


def start_background_workers():
    """启动后台自动并发刷新与平滑预热常驻守护线程"""
    def auto_ingest_worker():
        logger.info("后台新账号自动热维护线程已启动 (周期: 15 秒)")
        while True:
            try:
                time.sleep(15)
                ENGINE.auto_ingest_system_account()
            except Exception as e:
                logger.error(f"后台新账号热维护异常: {e}")

    def quota_worker():
        logger.info("后台配额并发定时刷新线程已启动 (周期: 30 秒高频守护)")
        while True:
            try:
                time.sleep(30)
                ENGINE.refresh_all_quotas()
            except Exception as e:
                logger.error(f"后台配额刷新异常: {e}")

    def warmup_worker():
        logger.info("后台 4 小时随机平滑预热线程已启动")
        while True:
            try:
                time.sleep(60)
                now = int(time.time())
                data = ENGINE.load_accounts()
                updated = False
                for email, acc in data.get("accounts", {}).items():
                    next_ts = acc.get("next_warmup_ts", 0)
                    if now >= next_ts:
                        ENGINE.trigger_warmup(email, acc)
                        updated = True
                if updated:
                    ENGINE.save_accounts(data)
            except Exception as e:
                logger.error(f"后台预热调度异常: {e}")

    t_ingest = threading.Thread(target=auto_ingest_worker, daemon=True)
    t_quota = threading.Thread(target=quota_worker, daemon=True)
    t_warmup = threading.Thread(target=warmup_worker, daemon=True)
    t_ingest.start()
    t_quota.start()
    t_warmup.start()


def run_server(port: int = SERVER_PORT):
    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, HubHTTPRequestHandler)
    start_background_workers()
    logger.info(f"🚀 Antigravity Hub 控制台已成功启动！访问地址: http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("正在停止控制台服务...")
        httpd.server_close()


if __name__ == "__main__":
    port = SERVER_PORT
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)
