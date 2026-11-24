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
import datetime
import uuid
import hashlib
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


__version__ = "4.4.0"
__canonical_version_tag__ = "20261124-v4.4.0-SCHEME_A_ISOLATION_FOUR_TIER_GOLD_NEON"
__last_updated__ = "2026-11-24 13:30:00"
__canonical_doctrine__ = "Antigravity Hub v4.4.0：方案A轻量化强隔离(独立浏览器容器、独立installation_id、低并发错峰防扫池、单账号代理)与四档分级(付费/学生/免费PRO/FREE，能用Gemini 4 Neon一律黄金背景)"

# 纳管并注册导入引擎兼容别名，彻底根除跨平台模块丢失隐患
from hub import importer as import_accounts_hub
sys.modules["import_accounts_hub"] = import_accounts_hub



# 配置常量
BASE_DATA_DIR = os.environ.get("ANTIGRAVITY_HUB_DIR", os.path.expanduser("~/.antigravity_hub"))
HUB_DIR = os.path.join(BASE_DATA_DIR, "data")
ACCOUNTS_HUB_FILE = os.path.join(HUB_DIR, "accounts_hub.json")
WARMUP_HUB_FILE = os.path.join(HUB_DIR, "warmup_hub.json")
WARMUP_SCHEDULE_PATH = os.path.join(HUB_DIR, "warmup_schedule.json")
AUTO_ROTATION_CONFIG_PATH = os.path.join(BASE_DATA_DIR, "auto_rotation_config.json")
HUB_SETTINGS_PATH = os.path.join(HUB_DIR, "hub_settings.json")
MANUAL_OVERRIDE_LOCK_PATH = os.path.join(BASE_DATA_DIR, "manual_override_lock.json")


HTMX_STATIC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "htmx.min.js")
try:
    with open(HTMX_STATIC_PATH, "rb") as _f:
        HTMX_JS_BYTES = _f.read()
except Exception:
    HTMX_JS_BYTES = b""

FAVICON_PNG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.png")
try:
    with open(FAVICON_PNG_PATH, "rb") as _f:
        FAVICON_PNG_BYTES = _f.read()
except Exception:
    FAVICON_PNG_BYTES = b""

LOGO_PNG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
try:
    with open(LOGO_PNG_PATH, "rb") as _f:
        LOGO_PNG_BYTES = _f.read()
except Exception:
    LOGO_PNG_BYTES = b""

APP_ICON_512_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_icon_512.png")
try:
    with open(APP_ICON_512_PATH, "rb") as _f:
        APP_ICON_512_BYTES = _f.read()
except Exception:
    APP_ICON_512_BYTES = LOGO_PNG_BYTES

OAUTH_CREDS_PATH = os.path.expanduser("~/.gemini/oauth_creds.json")
GOOGLE_ACCOUNTS_PATH = os.path.expanduser("~/.gemini/google_accounts.json")

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
LOAD_CODE_ASSIST_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
GOOGLE_REGION_CHANGE_URL = "https://policies.google.com/country-association-form"
WARMUP_ENDPOINTS = [
    "https://daily-cloudcode-pa.googleapis.com/v1internal:generateContent",
    "https://cloudcode-pa.googleapis.com/v1internal:generateContent"
]


def build_region_change_url(email: str = "") -> str:
    """构造带账号预选的 Google 关联地区修改申请页面地址"""
    em = str(email or "").strip()
    if not em:
        return GOOGLE_REGION_CHANGE_URL
    return (
        "https://accounts.google.com/AccountChooser?Email="
        + urllib.parse.quote(em, safe="")
        + "&continue="
        + urllib.parse.quote(GOOGLE_REGION_CHANGE_URL, safe="")
    )

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


def get_installed_browser_candidates() -> List[Dict[str, Any]]:
    """
    返回当前系统可用浏览器候选列表（按优先级排序）：
    macOS: ego lite -> Google Chrome -> open
    Linux: Brave -> Chromium -> Google Chrome -> xdg-open
    """
    candidates = []
    if sys.platform == "darwin":
        # 1. 优先检查 ego lite
        ego_paths = [
            "/Applications/ego lite.app",
            os.path.expanduser("~/Applications/ego lite.app"),
        ]
        for p in ego_paths:
            if os.path.exists(p):
                candidates.append({"name": "ego lite", "path": p})
                break

        # 2. 检查 Google Chrome
        chrome_paths = [
            "/Applications/Google Chrome.app",
            os.path.expanduser("~/Applications/Google Chrome.app"),
        ]
        for p in chrome_paths:
            if os.path.exists(p):
                candidates.append({"name": "Google Chrome", "path": p})
                break
    elif sys.platform.startswith("linux"):
        import shutil
        for bin_name, name in [("brave", "Brave"), ("chromium", "Chromium"), ("google-chrome", "Google Chrome")]:
            p = shutil.which(bin_name)
            if p:
                candidates.append({"name": name, "path": p})
        if shutil.which("xdg-open"):
            candidates.append({"name": "Default", "path": "xdg-open"})

    return candidates


def get_account_browser_profile(email: str) -> str:
    """
    为每个账号分配永久专属的独立浏览器容器目录名（位于 ~/.antigravity_hub/browser_profiles/ 下）：
    1. 优先复用历史已存在且非空的 <safe_name> 目录避免丢登录态；
    2. 否则分配脱敏稳定的 acc_<sha256[:12]> 独立容器目录，彻底斩断跨账号 Cookie 串号。
    """
    clean = str(email or "").strip().lower()
    if not clean:
        return f"guest_{uuid.uuid4().hex[:8]}"
    safe_legacy = clean.replace("@", "_").replace(".", "_")
    legacy_dir = os.path.join(BASE_DATA_DIR, "browser_profiles", safe_legacy)
    if os.path.isdir(legacy_dir) and any(os.scandir(legacy_dir)):
        return safe_legacy
    digest = hashlib.sha256(clean.encode("utf-8")).hexdigest()[:12]
    return f"acc_{digest}"


def build_account_opener(proxy_url: str = "", ssl_ctx: Optional[ssl.SSLContext] = None):
    """按账号独立 proxy_url 构造 HTTP Opener，支持为重点 PRO 号绑定独立出口 IP"""
    ctx = ssl_ctx or ssl.create_default_context()
    handlers: List[Any] = [urllib.request.HTTPSHandler(context=ctx)]
    p_url = str(proxy_url or "").strip()
    if p_url:
        handlers.insert(0, urllib.request.ProxyHandler({"http": p_url, "https": p_url}))
    return urllib.request.build_opener(*handlers)


def launch_browser_for_auth(url: str, isolated: bool = True, profile_name: str = "") -> bool:
    """
    为解封、地区解锁或 OAuth 授权拉起独立容器浏览器 (默认强制 isolated=True，杜绝多账号 Cookie 串号)：
    - macOS: 优先 ego lite / Chrome，支持 --user-data-dir 独立容器；
    - Linux: 优先 Brave / Chromium / Chrome，支持 --user-data-dir 独立容器，兜底 xdg-open；
    """
    candidates = get_installed_browser_candidates()
    profile_dir = os.path.join(BASE_DATA_DIR, "browser_profiles", profile_name) if profile_name else None
    if profile_dir:
        os.makedirs(profile_dir, exist_ok=True)

    for cand in candidates:
        app_name = cand["name"]
        app_path = cand["path"]
        try:
            if sys.platform == "darwin":
                if isolated and profile_dir:
                    cmd = ["open", "-na", app_name, "--args", f"--user-data-dir={profile_dir}", url]
                    p = subprocess.Popen(cmd)
                    p.wait(timeout=1)
                    if p.returncode == 0:
                        logger.info(f"🚀 [浏览器调起] 已为授权/解封拉起独立容器 ({app_name}): {profile_dir}")
                        return True
                cmd = ["open", "-a", app_name, url]
                subprocess.Popen(cmd)
                logger.info(f"🚀 [浏览器调起] 已在现役 {app_name} 浏览器中打开目标 URL")
                return True
            elif sys.platform.startswith("linux"):
                if app_path == "xdg-open":
                    subprocess.Popen(["xdg-open", url])
                    return True
                cmd = [app_path]
                if isolated and profile_dir:
                    cmd.extend(["--new-window", f"--user-data-dir={profile_dir}", "--no-first-run", "--no-default-browser-check"])
                cmd.append(url)
                # 注入当前桌面显示环境变量，确保独立容器窗口在 Hyprland/Wayland/X11 正常弹出
                env = os.environ.copy()
                if "DISPLAY" not in env:
                    env["DISPLAY"] = ":0"
                uid = os.getuid()
                if "WAYLAND_DISPLAY" not in env:
                    for w in ["wayland-1", "wayland-0"]:
                        if os.path.exists(f"/run/user/{uid}/{w}"):
                            env["WAYLAND_DISPLAY"] = w
                            break
                if "XDG_RUNTIME_DIR" not in env:
                    env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
                subprocess.Popen(cmd, env=env)
                logger.info(f"🚀 [浏览器调起 Linux] 已拉起 {app_name} (isolated={isolated}): {url}")
                return True
        except Exception as e:
            logger.warning(f"⚠️ [浏览器调起] 拉起 {app_name} 异常: {e}，尝试下一个候选")

    # 保底：使用系统默认浏览器
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        logger.info(f"🚀 [浏览器调起] 已使用系统默认浏览器打开目标 URL")
        return True
    except Exception as e:
        logger.error(f"❌ [浏览器调起失败] 系统默认打开异常: {e}")
        return False


_HUB_WRITE_LOCK = threading.RLock()


def atomic_write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    with _HUB_WRITE_LOCK:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            tmp_path = f"{file_path}.tmp.{os.getpid()}.{time.time()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.replace(tmp_path, file_path)
            except OSError:
                try:
                    import shutil
                    shutil.move(tmp_path, file_path)
                except Exception as ex:
                    logger.warning(f"原子替换失败回退写入: {ex}")
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=indent, ensure_ascii=False)
                    try:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
                    except Exception:
                        pass
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


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except Exception:
        return default


def detect_account_has_neon(acc: Dict[str, Any]) -> bool:
    """
    判定账号底层是否具备 Gemini 4 Neon / Claude 5.5 满血权限（决定是否呈现黄金背景）：
    无论来源是付费 PRO、学生 PRO 还是 18 个月免费 PRO，凡能用 Gemini 4 Neon 一律返回 True。
    """
    if not isinstance(acc, dict):
        return False
    raw_has_5h = acc.get("has_5h")
    if isinstance(raw_has_5h, bool):
        has_5h = raw_has_5h
    else:
        g_q5h = (acc.get("gemini") or {}).get("quota_5h")
        c_q5h = (acc.get("claude") or {}).get("quota_5h")
        has_5h = (g_q5h is not None) or (c_q5h is not None)
    if not has_5h:
        return False
    c_mods = acc.get("claude_models") or []
    if c_mods:
        if any(("5-5" in str(m) or "5.5" in str(m) or "neon" in str(m).lower()) for m in c_mods):
            return True
    if str(acc.get("claude_version") or "").strip() == "5.5":
        return True
    if acc.get("has_neon") is True:
        return True
    return False


def classify_account_tier(acc: Dict[str, Any]) -> Tuple[str, str, bool, bool]:
    """
    权威四档账号来源分类判定（100% 零硬编码邮箱）：
      1. PAID_PRO    (付费 PRO): 常规付费订阅 PRO
      2. STUDENT_PRO (学生 PRO): 学生教育订阅 PRO
      3. FREE_PRO    (免费 PRO): 活动白嫖满血 PRO（黄金背景）或普通免费 PRO（青蓝背景）
      4. FREE        (FREE):     无 5H 滑动窗口，仅有周总配额限制
    支持 tier_override 手工覆写来源标签，同时底层保留 detect_account_has_neon(acc) 决定黄金满血渲染。
    返回: (tier, tier_display, is_pro, has_5h)
    """
    override = str(acc.get("tier_override") or "").strip().upper()
    if override == "PAID_PRO":
        return "PAID_PRO", "付费 PRO", True, True
    if override == "STUDENT_PRO":
        return "STUDENT_PRO", "学生 PRO", True, True
    if override == "FREE_PRO":
        return "FREE_PRO", "免费 PRO", True, True
    if override == "FREE":
        return "FREE", "FREE", False, False

    raw_has_5h = acc.get("has_5h")
    if isinstance(raw_has_5h, bool):
        has_5h = raw_has_5h
    else:
        g_q5h = (acc.get("gemini") or {}).get("quota_5h")
        c_q5h = (acc.get("claude") or {}).get("quota_5h")
        has_5h = (g_q5h is not None) or (c_q5h is not None)

    has_neon = detect_account_has_neon(acc)

    tier_raw = str(acc.get("tier") or "").strip().upper()
    if has_5h and tier_raw == "STUDENT_PRO":
        return "STUDENT_PRO", "学生 PRO", True, True
    if has_5h and has_neon:
        return "PAID_PRO", "付费 PRO", True, True
    if has_5h:
        return "FREE_PRO", "免费 PRO", True, True
    return "FREE", "FREE", False, False


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


def get_auto_rotation_config() -> Dict[str, Any]:
    """
    【全局自动轮换配置】读取自动轮换三态模式配置（彻底移除 Claude 轮转）。
    三态模式:
      - 'gemini':   默认，全局 Gemini 轮转 (付费 PRO + 免费 PRO + FREE 全池参与)
      - 'paid_pro': 付费 PRO 轮转 (仅限 PAID_PRO 付费账号参与 Gemini 轮转)
      - 'off':      彻底关闭轮转功能 (看门狗完全冻结)
    历史遗留的 'claude' / 'claude_first' 自动平滑降级至默认 'gemini'。
    """
    cfg = {"mode": "gemini", "enabled": True, "policy": "gemini_first", "updated_at": 0}
    if os.path.exists(AUTO_ROTATION_CONFIG_PATH):
        try:
            with open(AUTO_ROTATION_CONFIG_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    cfg.update(raw)
        except Exception:
            pass

    raw_mode = str(cfg.get("mode") or "").strip().lower()
    if raw_mode in ("gemini", "paid_pro", "off"):
        m = raw_mode
    elif not cfg.get("enabled", True):
        m = "off"
    elif cfg.get("policy") == "paid_pro_only":
        m = "paid_pro"
    else:
        m = "gemini"

    cfg["mode"] = m
    cfg["enabled"] = (m != "off")
    cfg["policy"] = "paid_pro_only" if m == "paid_pro" else "gemini_first"
    return cfg


def set_auto_rotation_config(mode: str = "gemini", enabled: Optional[bool] = None, policy: Optional[str] = None) -> Dict[str, Any]:
    """
    【全局自动轮换配置】持久化原子保存自动轮换三态模式 ('gemini' | 'paid_pro' | 'off')。
    """
    norm_mode = str(mode or "").strip().lower()
    if norm_mode not in ("gemini", "paid_pro", "off"):
        if enabled is False:
            norm_mode = "off"
        elif policy == "paid_pro_only":
            norm_mode = "paid_pro"
        else:
            norm_mode = "gemini"

    cfg = {
        "mode": norm_mode,
        "enabled": (norm_mode != "off"),
        "policy": "paid_pro_only" if norm_mode == "paid_pro" else "gemini_first",
        "updated_at": int(time.time()),
        "updated_by": "hub_ui"
    }
    atomic_write_json(AUTO_ROTATION_CONFIG_PATH, cfg)
    logger.info(f"💾 [轮换配置持久化] 三态模式已保存: mode={norm_mode} (enabled={cfg['enabled']}, policy={cfg['policy']}) -> {AUTO_ROTATION_CONFIG_PATH}")
    return cfg

def get_hub_settings() -> Dict[str, Any]:
    """
    【全局控制台设置】读取 Magpie 风格控制台设置。
    """
    defaults = {
        "rotation_strategy": "highest-quota",
        "gemini_threshold": 0.0,
        "claude_threshold": 0.0,
        "default_sort": "gemini_5h_desc",
        "hourly_warmup": True,
        "warmup_model": "dual",
        "warmup_stagger_sec": 60,
        "account_mask": False,
        "auto_refresh_sec": 5,
        "hide_exhausted": False,
        "table_density": "standard",
    }
    if os.path.isfile(HUB_SETTINGS_PATH):
        try:
            with open(HUB_SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception as e:
            logger.warning(f"读取设置文件异常: {e}")
    return defaults


def save_hub_settings(new_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    【全局控制台设置】持久化原子保存控制台设置。
    """
    cfg = get_hub_settings()
    cfg.update(new_cfg)
    cfg["updated_at"] = int(time.time())
    atomic_write_json(HUB_SETTINGS_PATH, cfg)
    logger.info(f"💾 [控制台设置持久化] 已保存设置 -> {HUB_SETTINGS_PATH}")
    return cfg



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


def _parse_iso_to_epoch(iso_str: str) -> int:
    if not iso_str or "T" not in str(iso_str):
        return 0
    try:
        clean_iso = str(iso_str).strip().replace("Z", "+00:00")
        return int(datetime.datetime.fromisoformat(clean_iso).timestamp())
    except Exception:
        return 0


class HubEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self._token_lock = threading.Lock()
        self.refreshing_now = False
        self._cached_accounts_data: Dict[str, Any] = {}
        self._5h_clock_obs: Dict[Tuple[str, str], Tuple[float, int]] = {}
        self._initial_quota_sync_done = threading.Event()
        self._ensure_storage()

    def _record_5h_clock_state(
        self,
        email: str,
        bucket: str,
        q_5h: float,
        rst_iso: str,
        bkt_dict: Dict[str, Any],
        sched_entry: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        权威分辨 Google 5h resetTime 是“已锁定真实倒计时”还是“未预热墙钟漂移 (now+18000s)”：
        - 已有真实消耗 (<0.999)、剩余 <= 17850s、近 5 分钟内有真实 HTTP 200 预热记录、
          或 >=10s 两次探测时钟未随墙钟前进 -> 确认真实倒计时并写入 reset_time_5h；
        - 否则（确认漂移未激活态）清空虚假/旧 reset_time_5h 并标记 warmup_active=False，以便错峰预热调度立即接管。
        """
        rst_str = str(rst_iso or "").strip()
        t_ts = _parse_iso_to_epoch(rst_str)
        if not rst_str or t_ts <= 0:
            bkt_dict["reset_time_5h"] = ""
            bkt_dict["warmup_active"] = False
            return

        now_t = time.time()
        rem = t_ts - now_t
        w_ts = max(
            int(bkt_dict.get("warmup_ts") or 0),
            int((sched_entry or {}).get(f"{bucket}_warmup_ts") or 0),
        )
        prev_obs = self._5h_clock_obs.get((email, bucket))
        self._5h_clock_obs[(email, bucket)] = (now_t, t_ts)

        is_locked_countdown = (
            (q_5h < 0.999 and rem <= 18060)
            or (rem <= 17850)
            or (w_ts > 0 and 0 <= (now_t - w_ts) <= 300 and abs(t_ts - (w_ts + 18000)) <= 180)
            or (prev_obs is not None and (now_t - prev_obs[0]) >= 10.0 and abs(t_ts - prev_obs[1]) <= 2 and t_ts > now_t)
        )
        if is_locked_countdown:
            bkt_dict["reset_time_5h"] = rst_str
            bkt_dict["warmup_active"] = True
        else:
            bkt_dict["reset_time_5h"] = ""
            bkt_dict["warmup_active"] = False

    def _ensure_storage(self):
        os.makedirs(HUB_DIR, exist_ok=True)
        # 若主存储不存在或有效数据极小，优先执行多源容灾恢复
        if not os.path.exists(ACCOUNTS_HUB_FILE) or os.path.getsize(ACCOUNTS_HUB_FILE) < 100:
            self._try_fallback_recovery()

    def _try_fallback_recovery(self) -> Dict[str, Any]:
        """
        【本地真源多重容灾熔断兜底】
        当主存储（如 SMB/NAS 网络挂载盘）脱机、断网或文件损坏变空时，
        从本地 APFS 磁盘自动寻找历史备份与原生账号池并恢复主存储。
        """
        candidate_paths = [
            os.path.expanduser("~/.antigravity_hub/accounts_hub.json"),
            os.path.expanduser("~/.antigravity_hub/data/accounts_hub.json"),
        ]
        for p in candidate_paths:
            if os.path.exists(p) and os.path.getsize(p) > 100:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if isinstance(d, dict) and len(d.get("accounts", {})) > 0:
                        logger.info(f"✨ [容灾自动恢复] 成功从本地 APFS 备份 ({p}) 恢复 {len(d['accounts'])} 个账号！")
                        try:
                            atomic_write_json(ACCOUNTS_HUB_FILE, d)
                        except Exception:
                            pass
                        return d
                except Exception as e:
                    logger.warning(f"从容灾源 {p} 读取失败: {e}")

        # 尝试从 ~/.antigravity_tools/accounts/ 扫描
        tools_acc_dir = os.path.expanduser("~/.antigravity_tools/accounts")
        if os.path.exists(tools_acc_dir):
            try:
                records = {}
                import glob
                for jf in glob.glob(os.path.join(tools_acc_dir, "*.json")):
                    try:
                        with open(jf, "r", encoding="utf-8") as f:
                            acc_doc = json.load(f)
                        email = acc_doc.get("email")
                        if email and "@" in email:
                            records[email] = acc_doc
                    except Exception:
                        pass
                if records:
                    logger.info(f"✨ [容灾自动恢复] 成功从 ~/.antigravity_tools/accounts 恢复 {len(records)} 个账号！")
                    recovered = {
                        "active_email": list(records.keys())[0],
                        "accounts": records,
                        "last_updated": int(time.time()),
                    }
                    try:
                        atomic_write_json(ACCOUNTS_HUB_FILE, recovered)
                    except Exception:
                        pass
                    return recovered
            except Exception as e:
                logger.warning(f"从 ~/.antigravity_tools/accounts 恢复失败: {e}")

        # 尝试通过 hub.importer 初始化吸纳
        try:
            from hub.importer import import_accounts_read_only
            if import_accounts_read_only(ACCOUNTS_HUB_FILE):
                with open(ACCOUNTS_HUB_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"执行 import_accounts_read_only 失败: {e}")

        return {"active_email": "", "accounts": {}}

    def load_accounts(self) -> Dict[str, Any]:
        with self.lock:
            data = None
            if os.path.exists(ACCOUNTS_HUB_FILE):
                try:
                    with open(ACCOUNTS_HUB_FILE, "r", encoding="utf-8") as f:
                        candidate = json.load(f)
                    if isinstance(candidate, dict) and len(candidate.get("accounts", {})) > 0:
                        data = candidate
                    elif isinstance(candidate, dict) and len(candidate.get("accounts", {})) == 0:
                        logger.warning("⚠️ 主存储 accounts_hub.json 账号池为 0，启动本地多源容灾恢复...")
                except Exception as e:
                    logger.error(f"读取 accounts_hub.json 失败: {e} (如网络文件系统断开)，启动容灾降级...")

            # 若主存储读取失败或账号数为0，优先复用内存缓存；若内存缓存亦无，执行容灾恢复
            if not data or len(data.get("accounts", {})) == 0:
                if self._cached_accounts_data and len(self._cached_accounts_data.get("accounts", {})) > 0:
                    logger.info(f"🛡️ 复用内存缓存账号池 ({len(self._cached_accounts_data['accounts'])} 个账号)，避免断网置空")
                    data = self._cached_accounts_data
                else:
                    data = self._try_fallback_recovery()

            if not data:
                data = {"active_email": "", "accounts": {}}

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

            if len(data.get("accounts", {})) > 0:
                self._cached_accounts_data = data
            return data

    def save_accounts(self, data: Dict[str, Any]) -> bool:
        with self.lock:
            # 🛑 【零账号冲刷物理阻断门禁 (Anti-Zero-Wipe Guard)】
            incoming_accounts = data.get("accounts", {})
            if len(incoming_accounts) == 0:
                cached_count = len(self._cached_accounts_data.get("accounts", {})) if self._cached_accounts_data else 0
                if cached_count > 0:
                    logger.critical(f"🛑 [零账号冲刷物理阻断] 拦截到异常清空指令！试图写入 0 个账号，但现有内存包含 {cached_count} 个账号！坚决拒绝写入并保留原状！")
                    return False
                if os.path.exists(ACCOUNTS_HUB_FILE) and os.path.getsize(ACCOUNTS_HUB_FILE) > 100:
                    try:
                        with open(ACCOUNTS_HUB_FILE, "r", encoding="utf-8") as f:
                            disk_data = json.load(f)
                        disk_count = len(disk_data.get("accounts", {}))
                        if disk_count > 0:
                            logger.critical(f"🛑 [零账号冲刷物理阻断] 拦截到异常清空指令！试图写入 0 个账号，但磁盘现有 {disk_count} 个账号！坚决拒绝覆盖！")
                            return False
                    except Exception:
                        pass

            data["last_updated"] = int(time.time())
            for em, acc_obj in incoming_accounts.items():
                if not acc_obj.get("id"):
                    acc_obj["id"] = str(uuid.uuid5(uuid.NAMESPACE_DNS, em))
                # 依真实模型矩阵严格判定 Claude 版本，杜绝虚假 5.5
                c_mods = acc_obj.get("claude_models") or []
                has_real_55 = any(("5-5" in m or "5.5" in m) for m in c_mods) if c_mods else (str(acc_obj.get("claude_version") or "") == "5.5")
                if not has_real_55:
                    acc_obj["claude_version"] = "4.6"
                    if not c_mods:
                        acc_obj["claude_models"] = ["claude-sonnet-4-6", "claude-opus-4-6-thinking"]
                else:
                    acc_obj["claude_version"] = "5.5"

                tier, tier_display, is_pro, has_5h = classify_account_tier(acc_obj)
                acc_obj["tier"] = tier
                acc_obj["tier_display"] = tier_display
                acc_obj["pro"] = is_pro
                acc_obj["has_5h"] = has_5h
                # 全账号兼容：付费 PRO 默认支持，或只要官方返回有效 gemini4 配额即标定支持
                has_valid_g4 = bool(acc_obj.get("gemini4") and isinstance(acc_obj.get("gemini4"), dict) and acc_obj.get("gemini4", {}).get("quota_weekly") is not None)
                acc_obj["gemini4_supported"] = (tier == "PAID_PRO") or has_valid_g4

                if not has_5h:
                    # FREE 账号仅有周配额，物理杜绝 5H 虚显 100% 满额
                    g_obj = acc_obj.setdefault("gemini", {})
                    c_obj = acc_obj.setdefault("claude", {})
                    g_obj["quota_5h"] = None
                    g_obj["reset_time_5h"] = ""
                    c_obj["quota_5h"] = None
                    c_obj["reset_time_5h"] = ""

                # 尊重官方真实配额：仅在非付费且未包含有效周配额时清理脏数据，绝不误杀官方下发的 Gemini 4
                if tier != "PAID_PRO" and not has_valid_g4 and acc_obj.get("gemini4") is not None:
                    acc_obj["gemini4"] = None

            if incoming_accounts:
                self._cached_accounts_data = data

            # 1. 写入主存储
            ok = atomic_write_json(ACCOUNTS_HUB_FILE, data)

            # 2. 🛡️ 本地 APFS 镜像双写容灾备份 (Dual-Write Local APFS Backup)
            local_backup_file = os.path.expanduser("~/.antigravity_hub/accounts_hub.json")
            try:
                os.makedirs(os.path.dirname(local_backup_file), exist_ok=True)
                atomic_write_json(local_backup_file, data)
            except Exception as e:
                logger.warning(f"写入本地 APFS 镜像备份失败: {e}")

            # 3. 🔄 同步到底层轮换池与工具索引 (杜绝双脑分裂与孤儿/已删账号复活)
            try:
                self.sync_external_pools(data)
            except Exception as e:
                logger.warning(f"同步外部账号池异常: {e}")

            return ok

    def sync_external_pools(self, data: Dict[str, Any]):
        """将 accounts_hub.json (唯一真源 SSOT) 严格同步至 ~/.antigravity_tools 与 antigravity_account_pool.json，并物理清理孤儿/已删账号"""
        accounts = data.get("accounts", {})
        if not accounts:
            return
        active_email = data.get("active_email", "")
        now_ts = int(time.time())
        os.makedirs(ANTIGRAVITY_TOOLS_ACCOUNTS_DIR, exist_ok=True)

        valid_ids = set()
        idx_accounts = []
        pool_entries = []
        current_account_id = None

        for email, acc in accounts.items():
            if not email or "@" not in email:
                continue
            acc_id = acc.get("id") or str(uuid.uuid5(uuid.NAMESPACE_DNS, email))
            acc["id"] = acc_id
            valid_ids.add(acc_id)
            is_active = (email == active_email)
            if is_active:
                current_account_id = acc_id

            detail_path = os.path.join(ANTIGRAVITY_TOOLS_ACCOUNTS_DIR, f"{acc_id}.json")
            existing_detail = {}
            if os.path.exists(detail_path):
                try:
                    with open(detail_path, "r", encoding="utf-8") as f:
                        existing_detail = json.load(f)
                except Exception:
                    existing_detail = {}

            name = acc.get("name") or existing_detail.get("name") or email.split("@")[0]
            tok = existing_detail.get("token", {})
            if acc.get("refresh_token"):
                tok["refresh_token"] = acc["refresh_token"]
            if acc.get("access_token"):
                tok["access_token"] = acc["access_token"]
            if acc.get("expires_at") or acc.get("expiry_timestamp"):
                tok["expiry_timestamp"] = acc.get("expiry_timestamp") or acc.get("expires_at")

            q_meta = existing_detail.get("quota", {})
            q_meta["gemini_5h_remaining"] = acc.get("gemini", {}).get("quota_5h", 1.0)
            q_meta["gemini_weekly_remaining"] = acc.get("gemini", {}).get("quota_weekly", 1.0)
            q_meta["claude_5h_remaining"] = acc.get("claude", {}).get("quota_5h", 1.0)
            q_meta["claude_weekly_remaining"] = acc.get("claude", {}).get("quota_weekly", 1.0)

            detail_doc = {
                "id": acc_id,
                "email": email,
                "name": name,
                "token": tok,
                "quota": q_meta,
                "validation_blocked": bool(acc.get("validation_blocked", False)),
                "validation_url": acc.get("validation_url") if acc.get("validation_blocked") else None,
                "validation_blocked_reason": acc.get("validation_blocked_reason") if acc.get("validation_blocked") else None,
            }
            atomic_write_json(detail_path, detail_doc)

            idx_accounts.append({
                "id": acc_id,
                "email": email,
                "name": name,
                "disabled": False,
                "proxy_disabled": False,
                "created_at": acc.get("added_at") or now_ts,
                "last_used": now_ts if is_active else (acc.get("last_refreshed_ts") or now_ts),
            })

            pool_entries.append({
                "id": acc_id,
                "email": email,
                "name": name,
                "status": "active" if is_active else "standby",
                "last_5h_fraction": round(_safe_float((acc.get("gemini") or {}).get("quota_5h"), 1.0), 4),
                "last_used_time": float(now_ts) if is_active else 0.0,
                "cooldown_until": 0.0,
                "last_warmup_ts": acc.get("last_warmup_ts") or now_ts,
                "has_desktop_token": True,
            })

        # 清理 ~/.antigravity_tools/accounts/ 下不在 valid_ids 中的孤儿文件或已删账号文件
        import glob
        for jf in glob.glob(os.path.join(ANTIGRAVITY_TOOLS_ACCOUNTS_DIR, "*.json")):
            fn_id = os.path.splitext(os.path.basename(jf))[0]
            if fn_id not in valid_ids:
                try:
                    os.remove(jf)
                    logger.info(f"🧹 [三库统一清理] 已移除孤儿/已删账号详情文件: {os.path.basename(jf)}")
                except Exception:
                    pass

        tools_idx_path = os.path.join(ANTIGRAVITY_TOOLS_DIR, "accounts.json")
        idx_doc = {
            "version": "1.0",
            "accounts": idx_accounts,
            "current_account_id": current_account_id or (idx_accounts[0]["id"] if idx_accounts else ""),
            "current_target_ide": "antigravity",
        }
        atomic_write_json(tools_idx_path, idx_doc)

        pool_cfg_path = os.path.join(os.path.dirname(HUB_DIR), "antigravity_account_pool.json")
        atomic_write_json(pool_cfg_path, pool_entries)

    def sync_from_local_language_server(self, data: Optional[Dict[str, Any]] = None) -> bool:
        """
        【零风控本地守护直连】从本机运行中的 Antigravity language_server (127.0.0.1)
        GetUserStatus 接口实时读取当前活跃账号的 Gemini 4 Argon 周额度与 Claude 5.5 模型矩阵。
        100% 本地回环通信，0 外部网络请求，0 风控风险！
        """
        import glob
        daemon_dir = os.path.expanduser("~/.gemini/antigravity/daemon")
        if not os.path.isdir(daemon_dir):
            return False

        own_data = (data is None)
        if own_data:
            data = self.load_accounts()
        accounts = data.get("accounts", {})
        if not accounts:
            return False

        updated_any = False
        daemon_files = sorted(
            glob.glob(os.path.join(daemon_dir, "*.json")),
            key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
            reverse=True
        )
        for jf in daemon_files:
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    d_info = json.load(f)
                pid = d_info.get("pid")
                http_port = d_info.get("httpPort")
                csrf_token = d_info.get("csrfToken")
                if not pid or not http_port or not csrf_token:
                    continue
                try:
                    os.kill(int(pid), 0)
                except OSError:
                    continue

                url = f"http://127.0.0.1:{http_port}/exa.language_server_pb.LanguageServerService/GetUserStatus"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    headers={
                        "Content-Type": "application/json",
                        "x-codeium-csrf-token": str(csrf_token)
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    resp_j = json.loads(resp.read().decode("utf-8", errors="ignore"))

                u_status = resp_j.get("userStatus", {})
                email = (u_status.get("email") or "").strip().lower()
                if not email or email not in accounts:
                    continue

                old_active = data.get("active_email", "")
                prev_active_g4 = accounts.get(old_active, {}).get("gemini4") if (old_active and old_active != email and old_active in accounts) else None
                if old_active != email:
                    data["active_email"] = email
                    updated_any = True
                    if old_active and old_active in accounts:
                        try:
                            self.refresh_single_account_quota(old_active, accounts[old_active])
                        except Exception:
                            pass
                    try:
                        self.refresh_single_account_quota(email, accounts[email])
                    except Exception:
                        pass

                acc = accounts[email]

                # 🚀【第一真源：本地原生 RetrieveUserQuotaSummary 直连】
                # 100% 对齐 IDE "Models & Usage" 弹窗核心接口，读取物理隔离的 5 大配额分组
                g4_from_ls_summary = False
                try:
                    q_url = f"http://127.0.0.1:{http_port}/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary"
                    q_req = urllib.request.Request(
                        q_url,
                        data=b'{"forceRefresh": true}',
                        headers={
                            "Content-Type": "application/json",
                            "x-codeium-csrf-token": str(csrf_token)
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(q_req, timeout=3) as q_resp:
                        q_res = json.loads(q_resp.read().decode("utf-8", errors="ignore"))
                        q_groups = q_res.get("response", {}).get("groups", [])
                        ls_seen_any_bucket = False
                        ls_seen_5h_bucket = False
                        ls_pending_5h: Dict[str, Tuple[float, str]] = {}
                        for grp in q_groups:
                            grp_name = grp.get("displayName", "")
                            is_g4_grp = ("gemini 4" in grp_name.lower() or "argon" in grp_name.lower())
                            for bkt in grp.get("buckets", []):
                                bid = bkt.get("bucketId", "")
                                rem = bkt.get("remainingFraction")
                                rst = bkt.get("resetTime")
                                if rem is not None:
                                    ls_seen_any_bucket = True
                                    val = float(rem)
                                    if bid == "gemini-weekly":
                                        g_d = acc.setdefault("gemini", {})
                                        g_d["quota_weekly"] = val
                                        if rst:
                                            g_d["reset_time_weekly"] = str(rst)
                                            g_d["reset_time"] = str(rst)
                                        updated_any = True
                                    elif bid == "gemini-5h":
                                        ls_seen_5h_bucket = True
                                        ls_pending_5h["gemini"] = (val, str(rst or ""))
                                    elif bid == "3p-weekly":
                                        c_d = acc.setdefault("claude", {})
                                        c_d["quota_weekly"] = val
                                        if rst:
                                            c_d["reset_time_weekly"] = str(rst)
                                            c_d["reset_time"] = str(rst)
                                        updated_any = True
                                    elif bid == "3p-5h":
                                        ls_pending_5h["claude"] = (val, str(rst or ""))
                                    elif is_g4_grp or "argon" in bid.lower() or "gemini-4" in bid.lower():
                                        g4_d = acc.setdefault("gemini4", {})
                                        g4_d["quota_weekly"] = val
                                        if rst:
                                            g4_d["reset_time_weekly"] = str(rst)
                                        g4_from_ls_summary = True
                                        updated_any = True
                        if ls_seen_any_bucket:
                            acc["has_5h"] = ls_seen_5h_bucket
                            if ls_seen_5h_bucket:
                                if "gemini" in ls_pending_5h:
                                    g_val, g_rst = ls_pending_5h["gemini"]
                                    g_d = acc.setdefault("gemini", {})
                                    g_d["quota_5h"] = g_val
                                    self._record_5h_clock_state(email, "gemini", g_val, g_rst, g_d)
                                if "claude" in ls_pending_5h:
                                    c_val, c_rst = ls_pending_5h["claude"]
                                    c_d = acc.setdefault("claude", {})
                                    c_d["quota_5h"] = c_val
                                    self._record_5h_clock_state(email, "claude", c_val, c_rst, c_d)
                            else:
                                acc.setdefault("gemini", {})["quota_5h"] = None
                                acc["gemini"]["reset_time_5h"] = ""
                                acc["gemini"]["warmup_active"] = False
                                acc.setdefault("claude", {})["quota_5h"] = None
                                acc["claude"]["reset_time_5h"] = ""
                                acc["claude"]["warmup_active"] = False
                            updated_any = True
                except Exception as qe:
                    logger.debug(f"本地 language_server RetrieveUserQuotaSummary 直连探测跳过: {qe}")

                # 🎯【第二真源：GetUserStatus 提取可用模型矩阵与精确 Argon 判定】
                configs = u_status.get("cascadeModelConfigData", {}).get("clientModelConfigs", [])
                if not configs:
                    continue

                argon_found = None
                argon_disabled = False
                c_models = []
                for m in configs:
                    m_id = str(m.get("modelId") or "")
                    m_lbl = str(m.get("label") or "")
                    q_info = m.get("quotaInfo") or {}
                    rem = q_info.get("remainingFraction")
                    reset = str(q_info.get("resetTime") or "")
                    m_id_low = m_id.lower()
                    m_lbl_low = m_lbl.lower()

                    if "claude" in m_id_low:
                        c_models.append(m_id)

                    # 严格聚焦 Argon 模型，彻底忽略内部未发布的 gemini-4-carbon-disabled 干扰！
                    if "argon" in m_id_low or "argon" in m_lbl_low:
                        if "disabled" in m_id_low or rem is None:
                            argon_disabled = True
                        elif rem is not None and argon_found is None:
                            argon_found = {
                                "quota_weekly": float(rem),
                                "reset_time_weekly": reset
                            }

                ls_has_55 = any(("5-5" in cm or "5.5" in cm) for cm in c_models)
                # 只有在 RetrieveUserQuotaSummary 未明确抓取到 Argon 时，才采用 GetUserStatus 进行兜底判定
                if not g4_from_ls_summary:
                    if (argon_disabled and argon_found is None) or (c_models and not ls_has_55 and argon_found is None):
                        if acc.get("gemini4") is not None:
                            acc["gemini4"] = None
                            updated_any = True
                    elif argon_found is not None:
                        # 发现有效 Argon 周配额，更新账号独立周额度
                        prev_g4 = acc.get("gemini4")
                        if prev_g4 != argon_found:
                            acc["gemini4"] = argon_found
                            updated_any = True

                if c_models:
                    has_55 = any(("5-5" in cm or "5.5" in cm) for cm in c_models)
                    new_ver = "5.5" if has_55 else "4.6"
                    if acc.get("claude_models") != c_models or acc.get("claude_version") != new_ver:
                        acc["claude_models"] = c_models
                        acc["claude_version"] = new_ver
                        updated_any = True
            except Exception as e:
                logger.debug(f"本地 language_server 状态同步跳过 ({jf}): {e}")

        if updated_any and own_data:
            self.save_accounts(data)
        return updated_any

    def auto_ingest_system_account(self) -> Optional[Tuple[str, bool]]:
        """
        【新登录账号 100% 自动热维护纳管】
        实时从 macOS Keychain 与系统配置中嗅探当前活跃登录账号，
        若发现新登录账号或凭据更新，自动无感热纳管至 accounts_hub.json 并初始化配额。
        返回: (email, is_new) 或 None
        """
        try:
            kd = None
            if sys.platform == "darwin":
                cmd = ["security", "find-generic-password", "-s", "gemini", "-a", "antigravity", "-w"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout.strip():
                    raw = res.stdout.strip()
                    if raw.startswith("go-keyring-base64:"):
                        raw = raw.replace("go-keyring-base64:", "")
                    dec = base64.b64decode(raw).decode("utf-8")
                    kd = json.loads(dec)
            elif sys.platform.startswith("linux"):
                cmd = ["secret-tool", "lookup", "service", "gemini", "username", "antigravity"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout.strip():
                    raw = res.stdout.strip()
                    if raw.startswith("go-keyring-base64:"):
                        raw = base64.b64decode(raw[len("go-keyring-base64:"): ]).decode("utf-8")
                    kd = json.loads(raw)

            if not kd:
                return None

            at = kd.get("token", {}).get("access_token") or kd.get("access_token")
            rt = kd.get("token", {}).get("refresh_token") or kd.get("refresh_token")
            if not at or not rt:
                return None

            # 探测当前 Token 所属邮箱 (优先 kd 中的 id_token_email，其次 TokenInfo，兜底 google_accounts.json)
            detected_email = kd.get("id_token_email", "").strip().lower()
            if not detected_email:
                try:
                    t_url = f"https://oauth2.googleapis.com/tokeninfo?access_token={at}"
                    req = urllib.request.Request(t_url, headers={"User-Agent": "AntigravityHub/2.1"})
                    ctx = ssl.create_default_context()
                    with urllib.request.urlopen(req, timeout=3, context=ctx) as r:
                        t_info = json.loads(r.read().decode("utf-8"))
                        detected_email = t_info.get("email", "").strip().lower()
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
                # 立即拉取实时配额与三档分类
                try:
                    self.refresh_single_account_quota(detected_email, new_acc)
                except Exception as e:
                    logger.warning(f"新账号初始化配额异常: {e}")

                accounts[detected_email] = new_acc
                data["accounts"] = accounts
                data["active_email"] = detected_email
                self.save_accounts(data)
                logger.info(f"✅ [热维护自动纳管成功] 账号 {detected_email} 已纳入 Hub 账本并设为活跃账号！")
                return detected_email, True
            else:
                # 已存在，检查是否需要同步更新 refresh_token 或基于时间戳单调双向同步 access_token
                existing = accounts[detected_email]
                updated = False
                kd_exp = 0
                exp_str = kd.get("token", {}).get("expiry") or kd.get("expiry") or ""
                if exp_str:
                    try:
                        kd_exp = int(datetime.datetime.fromisoformat(exp_str.replace("Z", "+00:00")).timestamp())
                    except Exception:
                        pass

                hub_exp = int(existing.get("expires_at", 0) or existing.get("expiry_timestamp", 0))
                sync_local_needed = False
                hub_pushed_to_system = False
                if existing.get("refresh_token") != rt:
                    existing["refresh_token"] = rt
                    existing["access_token"] = at
                    existing["expires_at"] = kd_exp if kd_exp > now_ts else (now_ts + 3600)
                    existing["expiry_timestamp"] = existing["expires_at"]
                    updated = True
                    sync_local_needed = True
                elif kd_exp > 0 and kd_exp > hub_exp + 60:
                    # 系统钥匙串中的 Token 更新（例如 IDE 自身续签），反向同步回 Hub 账本
                    existing["access_token"] = at
                    existing["expires_at"] = kd_exp
                    existing["expiry_timestamp"] = kd_exp
                    updated = True
                    sync_local_needed = True
                elif kd_exp > 0 and hub_exp > kd_exp + 60 and hub_exp > now_ts + 300:
                    # 严格判定系统钥匙串中的 Token 过期时间戳滞后于 Hub 账本，主动回补同步
                    hub_at = existing.get("access_token", "")
                    if hub_at and hub_at != at:
                        logger.info(f"🛡️ [钥匙串滞后自愈] 系统密钥环凭据时间戳滞后 ({kd_exp} < {hub_exp})，主动同步最新 Token 至系统...")
                        self.sync_active_credentials_to_system(detected_email, hub_at, rt, hub_exp)
                        hub_pushed_to_system = True
                if data.get("active_email") != detected_email:
                    # 人工干预保护优先门禁：若当前处于有效锁定保护期，杜绝被意外覆盖
                    lock_info = get_manual_override_lock()
                    if lock_info and lock_info.get("manual_account") and lock_info.get("locked_until", 0) > time.time():
                        locked_acc = lock_info.get("manual_account")
                        if locked_acc != detected_email:
                            logger.warning(
                                f"🛡️ [人工锁抗回弹防御] 系统凭据检测为 {detected_email}，但当前处于用户指定保护期 ({locked_acc})！"
                                f"保持锁定状态，跳过自动覆盖（严禁后台反向自激 kill 进程）。"
                            )
                            return locked_acc, False
                    old_active = data.get("active_email", "")
                    data["active_email"] = detected_email
                    sync_local_needed = True
                    # 发生活跃账号切换时，立即刷新原账号与新账号的真实配额，防止刚用完的账号滞留显示 100%
                    if old_active and old_active in accounts and old_active != detected_email:
                        try:
                            self.refresh_single_account_quota(old_active, accounts[old_active])
                        except Exception as ex:
                            logger.warning(f"切换后刷新原账号 {old_active} 配额异常: {ex}")
                    try:
                        self.refresh_single_account_quota(detected_email, existing)
                    except Exception as ex:
                        logger.warning(f"切换后刷新新账号 {detected_email} 配额异常: {ex}")
                    updated = True

                # 若系统钥匙串 Token 有效且未由 Hub 回补过，核验 ~/.gemini/oauth_creds.json / app_storage.json 是否滞后脱节
                if not hub_pushed_to_system and (kd_exp == 0 or kd_exp > now_ts + 60):
                    if not sync_local_needed:
                        try:
                            if not os.path.exists(OAUTH_CREDS_PATH) or not os.path.exists(GOOGLE_ACCOUNTS_PATH):
                                sync_local_needed = True
                            else:
                                with open(OAUTH_CREDS_PATH, "r", encoding="utf-8") as cf:
                                    if json.load(cf).get("access_token") != at:
                                        sync_local_needed = True
                                if not sync_local_needed:
                                    with open(GOOGLE_ACCOUNTS_PATH, "r", encoding="utf-8") as gf:
                                        if json.load(gf).get("active") != detected_email:
                                            sync_local_needed = True
                                if not sync_local_needed:
                                    app_st_p = os.path.expanduser("~/.config/Antigravity/app_storage.json")
                                    if os.path.isfile(app_st_p):
                                        with open(app_st_p, "r", encoding="utf-8") as af:
                                            if json.load(af).get("agy.onboarding.lastLoginUsername") != detected_email:
                                                sync_local_needed = True
                        except Exception:
                            sync_local_needed = True

                    if sync_local_needed:
                        try:
                            from core.switcher import AntigravityPhysicalManager
                            sync_exp = kd_exp if kd_exp > now_ts else (int(existing.get("expires_at", 0) or existing.get("expiry_timestamp", 0)) or (now_ts + 3600))
                            AntigravityPhysicalManager().sync_local_credentials(detected_email, at, rt, sync_exp)
                        except Exception as se:
                            logger.warning(f"同步本地凭据文件至系统钥匙串当前状态异常: {se}")

                if self.sync_from_local_language_server(data):
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

    def fetch_live_quota(self, access_token: str, proxy_url: str = "") -> Tuple[Dict[str, float], Dict[str, str], Optional[str]]:
        """
        拉取配额，返回: (quotas, resets, validation_url)
        若触发 403 VALIDATION_REQUIRED，validation_url 会携带解封链接
        """
        payload = json.dumps({"project": "aicode-consumers"}).encode("utf-8")
        req = urllib.request.Request(
            QUOTA_ENDPOINT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": "antigravity/2.31.0",
                "X-Goog-Api-Client": "gl-go/1.22.0 gdcl/0.0.0"
            },
            method="POST",
            data=payload
        )
        ctx = ssl.create_default_context()
        quotas: Dict[str, float] = {}
        resets: Dict[str, str] = {}
        try:
            if proxy_url:
                opener = build_account_opener(proxy_url, ctx)
                resp_cm = opener.open(req, timeout=10)
            else:
                resp_cm = urllib.request.urlopen(req, timeout=10, context=ctx)
            with resp_cm as resp:
                body_str = _safe_decode_resp(resp.read())
                data = json.loads(body_str)
            for group in data.get("groups", []):
                grp_name = group.get("displayName", "")
                is_g4_grp = ("gemini 4" in grp_name.lower() or "gemini-4" in grp_name.lower() or "argon" in grp_name.lower())
                for bucket in group.get("buckets", []):
                    b_id = bucket.get("bucketId", "")
                    rem = bucket.get("remainingFraction")
                    reset = bucket.get("resetTime")
                    if b_id:
                        quotas[b_id] = float(rem) if rem is not None else 0.0
                        if reset:
                            resets[b_id] = str(reset)
                        if is_g4_grp or "gemini-4" in b_id.lower() or "gemini4" in b_id.lower() or "argon" in b_id.lower():
                            quotas["gemini4-weekly"] = float(rem) if rem is not None else 0.0
                            if reset:
                                resets["gemini4-weekly"] = str(reset)
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

    def fetch_available_models(self, access_token: str, proxy_url: str = "") -> Tuple[str, List[str]]:
        """
        探测账号支持的模型矩阵，精准区分满血 Gemini 4 Neon / Claude 5.5 与普通 Claude 4.6
        返回: (claude_version: "5.5" | "4.6", claude_models: List[str])
        """
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
            if proxy_url:
                opener = build_account_opener(proxy_url, ctx)
                resp_cm = opener.open(req, timeout=8)
            else:
                resp_cm = urllib.request.urlopen(req, timeout=8, context=ctx)
            with resp_cm as resp:
                body_str = _safe_decode_resp(resp.read())
                data = json.loads(body_str)
            c_models = []
            has_55 = False
            has_46 = False
            for g in data.get("agentModelSorts", []):
                for grp in g.get("groups", []):
                    for m in grp.get("modelIds", []):
                        if "claude" in m:
                            c_models.append(m)
                            if "5-5" in m or "5.5" in m:
                                has_55 = True
                            elif "4-6" in m or "4.6" in m:
                                has_46 = True
            ver = "5.5" if has_55 else ("4.6" if has_46 else "4.6")
            return ver, c_models
        except Exception as e:
            logger.debug(f"探测模型矩阵失败: {e}")
            return "4.6", []

    def check_account_region_eligibility(self, access_token: str, proxy_url: str = "") -> Tuple[Optional[bool], str, str]:
        """
        调用 Google 官方 v1internal:loadCodeAssist 毫秒级探测账号关联地区是否受限 (UNSUPPORTED_LOCATION)。
        返回: (is_restricted: True | False | None, region_code: "CN" | "", reason_code: str)
        - 当 ineligibleTiers 含 UNSUPPORTED_LOCATION 时返回 (True, "CN", "UNSUPPORTED_LOCATION")
        - 当接口正常返回且无地区受限时返回 (False, "", "")，自动解除历史受限标记
        - 网络异常时返回 (None, "", "") 保持原缓存状态不闪烁
        """
        if not access_token:
            return None, "", ""
        payload = json.dumps({
            "metadata": {
                "ideType": "ANTIGRAVITY",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }
        }).encode("utf-8")
        req = urllib.request.Request(
            LOAD_CODE_ASSIST_ENDPOINT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "User-Agent": "antigravity/1.19.6 linux/amd64",
            },
            method="POST",
            data=payload,
        )
        ctx = ssl.create_default_context()
        try:
            if proxy_url:
                opener = build_account_opener(proxy_url, ctx)
                resp_cm = opener.open(req, timeout=8)
            else:
                resp_cm = urllib.request.urlopen(req, timeout=8, context=ctx)
            with resp_cm as resp:
                body_str = _safe_decode_resp(resp.read())
                data = json.loads(body_str)
            inelig = data.get("ineligibleTiers") or []
            for tier_item in inelig:
                if isinstance(tier_item, dict) and str(tier_item.get("reasonCode", "")).upper() == "UNSUPPORTED_LOCATION":
                    return True, "CN", "UNSUPPORTED_LOCATION"
            if data.get("currentTier") is not None or isinstance(inelig, list):
                return False, "", ""
            return None, "", ""
        except Exception as e:
            logger.debug(f"探测账号关联地区资格失败: {e}")
            return None, "", ""


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

    def sync_active_credentials_to_system(self, email: str, access_token: str, refresh_token: str, expiry_ts: float) -> bool:
        """
        【活跃账号全端凭据强一致性同步 · 物理对齐 Mac 原版与 Linux Secret Service】
        将最新签发的 access_token 同步至：
        1. Linux Secret Service (secret-tool) / macOS Keychain
        2. ~/.gemini/oauth_creds.json (保证 agy CLI 与扩展不过期)
        3. ~/.gemini/jetski-standalone-oauth-token (语言服务优先回退凭据)
        4. ~/.gemini/google_accounts.json (活跃指针)
        5. ~/.config/Antigravity/app_storage.json (防止 Electron 掉登录页)
        """
        try:
            from core.switcher import AntigravityPhysicalManager, format_rfc3339
            mgr = AntigravityPhysicalManager()
            exp_rfc = format_rfc3339(expiry_ts or (time.time() + 3600))
            if sys.platform == "darwin":
                mgr.write_to_macos_keychain(access_token, refresh_token, expiry_str=exp_rfc)
            elif sys.platform.startswith("linux"):
                mgr.write_to_linux_secret(access_token, refresh_token, email=email, expiry_str=exp_rfc)
            mgr.sync_local_credentials(email, access_token, refresh_token, expiry_ts)
            logger.info(f"🔄 [活跃凭据自愈同步] 账号 {email} 最新 Token 已原子同步至系统钥匙串与 ~/.gemini/ 凭据池！")
            return True
        except Exception as e:
            logger.error(f"❌ 同步活跃凭据至系统失败: {e}")
            return False

    def ensure_fresh_token(self, acc: Dict[str, Any], force: bool = False) -> Tuple[Optional[str], bool]:
        """
        按需 Token 缓存与临期刷新 (严格对齐原生 Antigravity Tools oauth.rs#L707-L728 与 Mac 原版)
        返回: (access_token, was_refreshed)
        """
        now = int(time.time())
        acc_id = acc.get("id", "")
        email = acc.get("email", "")
        at = acc.get("access_token")
        exp = acc.get("expires_at", 0) or acc.get("expiry_timestamp", 0)
        rt = acc.get("refresh_token")

        # 只要现有 access_token 存在且距离过期 > 15 分钟且非强制刷新，直接复用本地缓存 Token，0 次 OAuth 请求！
        if not force and at and exp > (now + TOKEN_REFRESH_SKEW_SECONDS):
            return at, False

        if not rt:
            logger.warning(f"账号 {email} 缺少 refresh_token，无法刷新")
            return None, False

        with self._token_lock:
            # 锁内二次检查（防止多线程并发同时重复触发 Google OAuth 续签）
            now = int(time.time())
            cur_at = acc.get("access_token")
            cur_exp = acc.get("expires_at", 0) or acc.get("expiry_timestamp", 0)
            if not force and cur_at and cur_exp > (now + TOKEN_REFRESH_SKEW_SECONDS):
                return cur_at, False
            if not force and email and self._cached_accounts_data:
                cached_acc = self._cached_accounts_data.get("accounts", {}).get(email)
                if cached_acc:
                    c_at = cached_acc.get("access_token")
                    c_exp = cached_acc.get("expires_at", 0) or cached_acc.get("expiry_timestamp", 0)
                    if c_at and c_exp > (now + TOKEN_REFRESH_SKEW_SECONDS):
                        acc["access_token"] = c_at
                        acc["expires_at"] = c_exp
                        acc["expiry_timestamp"] = c_exp
                        return c_at, False

            refreshed = self.refresh_google_token(rt)
            if not refreshed or "access_token" not in refreshed:
                logger.error(f"账号 {email} 刷新 Google Token 失败")
                return None, False

            at = refreshed.get("access_token")
            expires_in = refreshed.get("expires_in", 3600)
            exp = now + expires_in
            acc["access_token"] = at
            acc["expires_at"] = exp
            acc["expiry_timestamp"] = exp
            if email and self._cached_accounts_data and email in self._cached_accounts_data.get("accounts", {}):
                ca = self._cached_accounts_data["accounts"][email]
                ca["access_token"] = at
                ca["expires_at"] = exp
                ca["expiry_timestamp"] = exp
            if acc_id:
                self._sync_antigravity_tools_cache(acc_id, access_token=at, refresh_token=rt, expiry_ts=exp)

            # 核心契约：若当前被刷新的账号是活跃账号，必须立即无感同步至底层钥匙串与所有凭据真源！
            try:
                data = self.load_accounts()
                active_email = data.get("active_email", "")
                if email and email == active_email:
                    self.sync_active_credentials_to_system(email, at, rt, exp)
            except Exception as se:
                logger.warning(f"同步活跃账号凭据至系统异常: {se}")

            return at, True

    def refresh_single_account_quota(self, email: str, acc: Dict[str, Any]) -> bool:
        acc_id = acc.get("id", "")
        rt = acc.get("refresh_token")

        # 1. 严格先通过 ensure_fresh_token 确保 token 新鲜 (彻底消除因 401 导致的假死与死锁)
        at, was_refreshed = self.ensure_fresh_token(acc)
        if not at:
            logger.warning(f"账号 {email} 无法获取有效 access_token，跳过配额刷新")
            return False

        # 2. 向端点发起探测（有配置独立代理时透传 proxy_url，否则保持纯净单参调用）
        proxy_url = str(acc.get("proxy_url") or "").strip()
        quotas, resets, val_url = (
            self.fetch_live_quota(at, proxy_url=proxy_url) if proxy_url else self.fetch_live_quota(at)
        )
        if not quotas and not val_url and rt:
            # 捕获 401 或无效 Token，启动强制刷新一次性自愈
            logger.warning(f"⚠️ 账号 {email} 探测配额返回空或 401，立即启动强制 Token 续签自愈...")
            new_at, ok = self.ensure_fresh_token(acc, force=True)
            if ok and new_at:
                at = new_at
                quotas, resets, val_url = (
                    self.fetch_live_quota(at, proxy_url=proxy_url) if proxy_url else self.fetch_live_quota(at)
                )
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

            acc.setdefault("gemini", {})
            acc.setdefault("claude", {})

            sched_entry: Dict[str, Any] = {}
            if os.path.exists(WARMUP_SCHEDULE_PATH):
                try:
                    with open(WARMUP_SCHEDULE_PATH, "r", encoding="utf-8") as sf:
                        sched_all = json.load(sf)
                    if isinstance(sched_all, dict) and isinstance(sched_all.get(email), dict):
                        sched_entry = sched_all[email]
                except Exception:
                    pass

            # 权威物理门禁：仅当官方 retrieveUserQuotaSummary 返回 gemini-5h 桶才具备 5h 窗口（过滤 FREE 幽灵 3p-5h 误判）
            has_5h_bucket = ("gemini-5h" in quotas)
            acc["has_5h"] = has_5h_bucket

            acc["gemini"]["quota_weekly"] = quotas.get("gemini-weekly", acc["gemini"].get("quota_weekly", 1.0))
            if resets.get("gemini-weekly"):
                acc["gemini"]["reset_time_weekly"] = resets["gemini-weekly"]
                acc["gemini"]["reset_time"] = resets["gemini-weekly"]

            if has_5h_bucket:
                g_5h = quotas["gemini-5h"]
                acc["gemini"]["quota_5h"] = g_5h
                self._record_5h_clock_state(
                    email, "gemini", g_5h, resets.get("gemini-5h", ""), acc["gemini"], sched_entry=sched_entry
                )
            else:
                acc["gemini"]["quota_5h"] = None
                acc["gemini"]["reset_time_5h"] = ""
                acc["gemini"]["warmup_active"] = False

            acc["claude"]["quota_weekly"] = quotas.get("3p-weekly", acc["claude"].get("quota_weekly", 1.0))
            if resets.get("3p-weekly"):
                acc["claude"]["reset_time_weekly"] = resets["3p-weekly"]
                acc["claude"]["reset_time"] = resets["3p-weekly"]

            if has_5h_bucket and "3p-5h" in quotas:
                c_5h = quotas["3p-5h"]
                acc["claude"]["quota_5h"] = c_5h
                self._record_5h_clock_state(
                    email, "claude", c_5h, resets.get("3p-5h", ""), acc["claude"], sched_entry=sched_entry
                )
                if not resets.get("3p-weekly") and resets.get("3p-5h"):
                    acc["claude"]["reset_time"] = resets["3p-5h"]
            else:
                acc["claude"]["quota_5h"] = None if not has_5h_bucket else acc["claude"].get("quota_5h")
                acc["claude"]["reset_time_5h"] = "" if not has_5h_bucket else acc["claude"].get("reset_time_5h", "")
                if not has_5h_bucket:
                    acc["claude"]["warmup_active"] = False

            # Gemini 4 周配额专属提取 (若官方返回则记录，绝不伪造复制)
            g4_weekly_quota = quotas.get("gemini4-weekly")
            if g4_weekly_quota is not None:
                if "gemini4" not in acc or not isinstance(acc.get("gemini4"), dict):
                    acc["gemini4"] = {}
                acc["gemini4"]["quota_weekly"] = g4_weekly_quota
                if resets.get("gemini4-weekly"):
                    acc["gemini4"]["reset_time_weekly"] = resets["gemini4-weekly"]

        # 3. 探测模型矩阵并按权威四档规则校准（同时持久化独立 installation_id 与 has_neon 满血能力）
        try:
            proxy_url = str(acc.get("proxy_url") or "").strip()
            if not str(acc.get("installation_id") or "").strip():
                acc["installation_id"] = str(uuid.uuid4())
            g4_from_summary = (quotas.get("gemini4-weekly") is not None) if quotas else False
            c_ver, c_mods = self.fetch_available_models(at, proxy_url=proxy_url)
            if c_mods:
                acc["claude_models"] = c_mods
                acc["claude_version"] = c_ver
            has_neon = detect_account_has_neon(acc) or g4_from_summary
            acc["has_neon"] = bool(has_neon)
            tier, tier_display, is_pro, has_5h = classify_account_tier(acc)
            acc["tier"] = tier
            acc["tier_display"] = tier_display
            acc["pro"] = is_pro
            acc["has_5h"] = has_5h
            acc["gemini4_supported"] = bool(has_neon or tier in ("PAID_PRO", "STUDENT_PRO"))
            if not has_neon and tier not in ("PAID_PRO", "STUDENT_PRO") and not g4_from_summary:
                acc["gemini4"] = None
        except Exception:
            pass

        # 3.5 探测账号关联地区是否受限 (Google loadCodeAssist UNSUPPORTED_LOCATION)
        try:
            proxy_url = str(acc.get("proxy_url") or "").strip()
            is_reg_blocked, reg_code, reg_reason = self.check_account_region_eligibility(at, proxy_url=proxy_url)
            if is_reg_blocked is True:
                was_reg = bool(acc.get("region_restricted", False))
                acc["region_restricted"] = True
                acc["region_code"] = reg_code or "CN"
                acc["region_reason"] = reg_reason or "UNSUPPORTED_LOCATION"
                acc["region_change_url"] = build_region_change_url(email)
                if not was_reg:
                    logger.warning(f"🚩 [关联地区受限] 账号 {email} 被 Google 判定为 {acc['region_reason']}，已标注受限并开放解锁入口")
            elif is_reg_blocked is False:
                was_reg = bool(acc.get("region_restricted", False))
                acc["region_restricted"] = False
                acc["region_code"] = ""
                acc["region_reason"] = ""
                acc["region_change_url"] = ""
                if was_reg:
                    logger.info(f"🎉 [地区解锁成功] 账号 {email} 已通过地区审核，自动恢复可用状态！")
        except Exception:
            pass

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
            items = list(accounts.items())
            # 方案 A 防扫池关联：随机乱序 + 低并发(max_workers=2) + 轻量随机错峰抖动，彻底消除 6 路瞬间齐射指纹
            random.shuffle(items)
            enable_jitter = (os.environ.get("ANTIGRAVITY_FAST_TEST", "") != "1")

            def _worker(item):
                email, acc = item
                try:
                    if enable_jitter and len(items) > 1:
                        time.sleep(random.uniform(0.12, 0.38))
                    ok = self.refresh_single_account_quota(email, acc)
                    return (email, ok)
                except Exception as e:
                    logger.error(f"错峰刷新账号 {email} 配额失败: {e}")
                    return (email, False)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = executor.map(_worker, items)
                for email, ok in results:
                    if ok:
                        success_count += 1

            self.sync_from_local_language_server(data)
            self.save_accounts(data)
            logger.info(f"✅ 全池配额低并发错峰刷新完成！成功: {success_count}/{len(accounts)}")
            return success_count
        finally:
            self.refreshing_now = False

    def trigger_warmup(self, email: str, acc: Dict[str, Any], model_override: str = "") -> bool:
        """
        Hub 预热单账号直通入口，仅针对具备 5h 桶的 PRO 账号发送真实 1-token 生成激活
        """
        try:
            from core.switcher import AntigravityPhysicalManager
            mgr = AntigravityPhysicalManager()
            cfg = get_hub_settings()
            warmup_mode = str(cfg.get("warmup_model") or "dual")
            stagger_sec = int(cfg.get("warmup_stagger_sec") or 60)
            acc_entry = dict(acc)
            acc_entry["email"] = email
            res = mgr.warmup_single_account(
                acc_entry,
                force=True,
                model_override=model_override,
                warmup_mode=warmup_mode,
                stagger_sec=stagger_sec,
            )
            st = res.get("status")
            if st in ("success", "already_active"):
                logger.info(f"🔥 Hub 触发真实预热完成: {email} -> {res}")
                now = int(time.time())
                acc["last_warmup_ts"] = acc_entry.get("last_warmup_ts", now)
                if res.get("locked_reset_ts"):
                    acc["next_warmup_ts"] = res["locked_reset_ts"]
                if "gemini" in acc_entry and isinstance(acc_entry["gemini"], dict):
                    acc.setdefault("gemini", {}).update(acc_entry["gemini"])
                if "claude" in acc_entry and isinstance(acc_entry["claude"], dict):
                    acc.setdefault("claude", {}).update(acc_entry["claude"])
                self.refresh_single_account_quota(email, acc)
                return True
            else:
                logger.warning(f"⚠️ Hub 触发预热非成功: {email} -> {res}")
                return False
        except Exception as e:
            logger.error(f"❌ Hub 触发预热异常 {email}: {e}")
            return False

    def run_hourly_staggered_warmup(self, force: bool = False) -> int:
        """
        每小时随机错峰预热调度与立即批量激活入口：
        - 仅面向 PRO 账号，跳过 FREE 账号；
        - force=True 时按随机打散顺序向所有未激活 PRO 账号发送真实 1-token 请求；
        - force=False 时为未激活 PRO 账号排班并触发到期预热，绝不伪造 reset_time_5h。
        """
        try:
            from core.switcher import AntigravityPhysicalManager
            mgr = AntigravityPhysicalManager()
            cfg = get_hub_settings()
            warmup_mode = str(cfg.get("warmup_model") or "dual")
            stagger_sec = int(cfg.get("warmup_stagger_sec") or 60)
            data = self.load_accounts()
            accounts = [dict(v, email=k) for k, v in data.get("accounts", {}).items()]

            res = mgr.rebalance_and_align_staggered_ladder(
                accounts, force=force, stagger_sec=stagger_sec, warmup_mode=warmup_mode
            )
            due_count = 0
            if not force:
                due_count = mgr.check_and_trigger_due_staggered_warmup(
                    stagger_sec=stagger_sec, warmup_mode=warmup_mode
                )

            fresh_data = self.load_accounts()
            if fresh_data.get("accounts"):
                self.save_accounts(fresh_data)

            acted = int(res.get("warmed", 0) or 0) + due_count
            logger.info(
                f"🎯 [随机错峰预热闭环] PRO 总数: {res.get('count', 0)}, 本轮实激活: {res.get('warmed', 0)}, 到期触发: {due_count}"
            )
            return acted if acted > 0 else int(res.get("count", 0) or 0)
        except Exception as e:
            logger.error(f"❌ 随机错峰预热调度异常: {e}")
            return 0

    def switch_account(self, target_email: str) -> Tuple[bool, str]:
        # 物理中枢无缝接入：与额度用尽自动轮换 100% 共享完全一致的底层物理切换与脱壳接力唤醒
        # 注意：不设置人工锁定，看门狗依旧正常监控额度，额度用完后自动切换不受阻碍
        try:
            from core.switcher import AntigravityPhysicalManager, DEFAULT_RELAY_PROMPT
            mgr = AntigravityPhysicalManager()
            success = mgr.perform_real_switch(target_email, restart_app=True, relay_prompt=DEFAULT_RELAY_PROMPT, force=True, inject_recovery=True)
            if success:
                # 异步执行原账号与目标账号的真实配额并发刷新，绝不阻塞当前 HTTP 响应
                def _async_post_refresh(old_em, new_em):
                    try:
                        d = self.load_accounts()
                        accs = d.get("accounts", {})
                        if old_em and old_em in accs and old_em != new_em:
                            try:
                                self.refresh_single_account_quota(old_em, accs[old_em])
                            except Exception:
                                pass
                        if new_em in accs:
                            try:
                                self.refresh_single_account_quota(new_em, accs[new_em])
                            except Exception:
                                pass
                        self.save_accounts(d)
                    except Exception as ex:
                        logger.warning(f"异步配额刷新异常: {ex}")

                data = self.load_accounts()
                old_active = data.get("active_email", "")
                now_epoch = int(time.time())
                accs_map = data.get("accounts", {})
                if target_email in accs_map and isinstance(accs_map[target_email], dict):
                    accs_map[target_email]["last_used_time"] = now_epoch
                data["active_email"] = target_email
                data["last_updated"] = now_epoch
                self.save_accounts(data)

                threading.Thread(target=_async_post_refresh, args=(old_active, target_email), daemon=True).start()

                # 用户手动点击切换账号：建立 15 分钟人工保护锁，绝不永久关闭全局自动轮换模式！
                set_manual_override_lock(target_email, duration_sec=900, reason="用户手动切换")
                logger.info(f"🛡️ [人工切换保护] 已建立 15 分钟临时保护锁，保持自动轮换监控 (账号 {target_email} 额度用尽时将自动瀑布切走)！")
                logger.info(f"🚀 [物理切换成功] 目标账号 {target_email} 凭据已注入，Antigravity 正在平滑重载！")
                return True, f"物理切换至 {target_email} 成功，Antigravity 正在平滑重载！"
            else:
                logger.error(f"❌ 物理切换执行失败: {target_email}")
                return False, "物理切换执行失败"
        except Exception as e:
            logger.error(f"物理切换异常: {e}")
            return False, f"物理切换异常: {e}"



ENGINE = HubEngine()


def format_reset_time(iso_str: str) -> str:
    if not iso_str or iso_str == "--":
        return "--"
    try:
        # 解析 ISO UTC
        target_ts = 0
        if "T" in iso_str:
            clean_iso = iso_str.replace("Z", "+00:00")
            import datetime
            dt = datetime.datetime.fromisoformat(clean_iso)
            target_ts = dt.timestamp()
        else:
            return iso_str

        diff = int(target_ts - time.time())
        if diff <= 0:
            return "即将恢复"
        days = diff // 86400
        hours = (diff % 86400) // 3600
        mins = (diff % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {mins}m"
        if mins > 0:
            return f"{mins}m"
        return "<1m"
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


def format_quota_int_pct(ratio: Optional[float]) -> int:
    """标准四舍五入整数百分比 [0..100]，消除无意义小数位"""
    if ratio is None:
        return 0
    try:
        v = float(ratio)
    except (TypeError, ValueError):
        return 0
    clamped = max(0.0, min(1.0, v))
    return int(clamped * 100.0 + 0.5 + 1e-9)


def render_gemini4_cell(weekly_pct: Optional[float], reset_weekly_info: str = "") -> str:
    """
    渲染 Gemini 4 周额度单元格：
    - 若该账号具备 Gemini 4 额度 (weekly_pct is not None)，渲染单轨极简进度条与重置倒计时（零冗余标签）；
    - 若该账号未开通或无 Gemini 4 额度 (weekly_pct is None)，直接空着 (输出极简占位符或空白)。
    """
    if weekly_pct is None:
        return '<div class="q-cell q-cell-g4 q-cell-empty font-mono" title="此账号暂未开放 Gemini 4 权限"><span class="q-empty-dash font-mono text-muted">—</span></div>'

    raw_w = max(0.0, min(1.0, float(weekly_pct)))
    val_w = format_quota_int_pct(raw_w)
    c_w = "#16A34A" if val_w >= 50 else ("#EA580C" if val_w >= 15 else "#DC2626")

    if reset_weekly_info and reset_weekly_info not in ("--", "已就绪", "就绪"):
        reset_w_html = f'<span class="q-reset q-reset-w font-mono" title="Gemini 4 重置倒计时: {reset_weekly_info}">{reset_weekly_info}</span>'
    elif raw_w >= 0.999:
        reset_w_html = '<span class="q-reset q-reset-ready font-mono" title="Gemini 4 满血可用">满额</span>'
    else:
        reset_w_html = '<span class="q-reset q-reset-empty font-mono">--</span>'

    return f"""
    <div class="q-cell q-cell-g4" title="Gemini 4 配额: {val_w}%">
        <div class="q-row">
            <div class="q-track"><div class="q-fill" style="width: {min(100, max(0, val_w))}%; background: {c_w};"></div></div>
            <span class="q-val font-mono" style="color: {c_w};">{val_w}%</span>
            <div class="q-slot">{reset_w_html}</div>
        </div>
    </div>
    """


def render_tier_badge_html(tier: str, tier_display: str, has_neon: bool = False, email: str = "") -> str:
    """
    渲染四档账号类别徽标 (付费 PRO / 学生 PRO / 免费 PRO / FREE)：
    颜色铁律：凡能用 Gemini 4 Neon / Claude 5.5 满血权限（has_neon=True）一律黄金背景；
    普通非满血免费 PRO 为青蓝背景；FREE 为中性灰。支持点击循环切换来源类别。
    """
    is_gold = bool(has_neon or tier == "PAID_PRO")
    click_attr = ""
    cursor_css = ""
    if email and tier in ("PAID_PRO", "STUDENT_PRO", "FREE_PRO"):
        cycle_map = {"PAID_PRO": "STUDENT_PRO", "STUDENT_PRO": "FREE_PRO", "FREE_PRO": "PAID_PRO"}
        nxt = cycle_map.get(tier, "PAID_PRO")
        click_attr = f""" onclick="doCycleTier('{email}', '{nxt}'); event.preventDefault(); event.stopPropagation();" """
        cursor_css = "cursor:pointer;"

    if is_gold and tier != "FREE":
        tip = f"{tier_display}（满血 Gemini 4 Neon + Claude 5.5，点击切换来源类别）"
        return f'<span class="badge font-mono" style="background:#FEF3C7;color:#B45309;border:2px solid #D97706;padding:1px 6px;font-weight:900;{cursor_css}" title="{tip}"{click_attr}>{tier_display}</span>'
    if tier in ("FREE_PRO", "STUDENT_PRO"):
        tip = f"{tier_display}（Gemini 3.8 + Claude 4.6 + 5H/周双限，点击切换来源类别）"
        return f'<span class="badge font-mono" style="background:#E0F2FE;color:#0369A1;border:2px solid #0284C7;padding:1px 6px;font-weight:900;{cursor_css}" title="{tip}"{click_attr}>{tier_display}</span>'
    return f'<span class="badge font-mono" style="background:#F3F4F6;color:#4B5563;border:2px solid #9CA3AF;padding:1px 6px;font-weight:700;" title="FREE 免费账号：仅周限制（无 5H 滑动限制）">{tier_display}</span>'


def render_quota_cell(h5_pct: Optional[float], weekly_pct: float, reset_5h_info: str = "", reset_weekly_info: str = "", model_type: str = "gemini", claude_ver: str = "", has_5h: bool = True) -> str:
    raw_w = max(0.0, min(1.0, float(weekly_pct or 0.0)))
    val_w = format_quota_int_pct(raw_w)
    c_w = "#16A34A" if val_w >= 50 else ("#EA580C" if val_w >= 15 else "#DC2626")

    # 周度重置倒计时呈现 (彻底杜绝“就绪”假象，有倒计时显倒计时，无倒计时显满额)：
    if reset_weekly_info and reset_weekly_info not in ("--", "已就绪", "就绪"):
        reset_w_html = f'<span class="q-reset q-reset-w font-mono" title="周度配额重置倒计时: {reset_weekly_info}">{reset_weekly_info}</span>'
    elif raw_w >= 0.999:
        reset_w_html = '<span class="q-reset q-reset-ready font-mono" title="周度配额满血可用">满额</span>'
    else:
        reset_w_html = '<span class="q-reset q-reset-empty font-mono">--</span>'

    lbl_5h_cls = "tag-5h-g" if model_type == "gemini" else "tag-5h-c"
    lbl_w_cls = "tag-w-g" if model_type == "gemini" else "tag-w-c"

    cell_title = ""
    if model_type == "claude":
        cell_title = ' title="Claude 5.5"' if claude_ver == "5.5" else ' title="Claude"'
    elif model_type == "gemini":
        cell_title = ' title="Gemini"'

    # 方案 A：FREE 账号无 5H 滑动窗口，单轨居中展示 W 周配额，彻底消除虚假 5H 满额噪音
    if not has_5h:
        return f"""
    <div class="q-cell q-cell-weekly-only"{cell_title}>
        <div class="q-row">
            <span class="q-lbl {lbl_w_cls}">周</span>
            <div class="q-track"><div class="q-fill" style="width: {min(100, max(0, val_w))}%; background: {c_w};"></div></div>
            <span class="q-val font-mono" style="color: {c_w};">{val_w}%</span>
            <div class="q-slot">{reset_w_html}</div>
        </div>
    </div>
    """

    raw_5h = max(0.0, min(1.0, float(h5_pct if h5_pct is not None else 0.0)))
    is_weekly_exhausted = (raw_w < 0.005)
    val_5h = 0 if is_weekly_exhausted else format_quota_int_pct(raw_5h)
    c_5h = "#16A34A" if val_5h >= 50 else ("#EA580C" if val_5h >= 15 else "#DC2626")

    if is_weekly_exhausted:
        tip = f"周度总配额已用尽 (0%)，5小时配额短路归零，等待周度重置: {reset_weekly_info}"
        reset_5h_html = f'<span class="q-reset q-reset-exhausted font-mono" title="{tip}">用尽</span>'
    elif reset_5h_info and reset_5h_info not in ("--", "已就绪", "就绪", "满额") and "d" not in reset_5h_info:
        reset_5h_html = f'<span class="q-reset q-reset-5h font-mono" title="5小时滑动配额真实倒计时: {reset_5h_info}">{reset_5h_info}</span>'
    else:
        reset_5h_html = '<span class="q-reset q-reset-ready font-mono" title="5小时周期尚未激活，等待随机错峰预热">待预热</span>'

    return f"""
    <div class="q-cell"{cell_title}>
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


def render_active_pill_html(
    active_email: str,
    oob: bool = False,
    active_tier: str = "",
    active_tier_display: str = "",
    active_has_neon: bool = False,
) -> str:
    oob_attr = ' hx-swap-oob="true"' if oob else ""
    short_name = active_email.split("@")[0] if "@" in active_email else (active_email or "未激活")
    lock_info = get_manual_override_lock()
    now_ts = time.time()

    tier_badge_inline = ""
    is_gold = bool(active_has_neon or active_tier == "PAID_PRO")
    lbl_text = active_tier_display or (
        "付费 PRO" if active_tier == "PAID_PRO" else
        ("学生 PRO" if active_tier == "STUDENT_PRO" else
        ("免费 PRO" if active_tier == "FREE_PRO" else ("FREE" if active_tier == "FREE" else "")))
    )
    if lbl_text:
        if is_gold and active_tier != "FREE":
            tier_badge_inline = f'<span class="active-tier-tag active-tier-paid font-mono">{lbl_text}</span>'
        elif active_tier in ("FREE_PRO", "STUDENT_PRO"):
            tier_badge_inline = f'<span class="active-tier-tag active-tier-freepro font-mono">{lbl_text}</span>'
        else:
            tier_badge_inline = f'<span class="active-tier-tag active-tier-free font-mono">{lbl_text}</span>'

    shield_svg = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#E11D48" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:3px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
    zap_svg = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:3px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'

    if lock_info and lock_info.get("manual_account") == active_email and lock_info.get("locked_until", 0) > now_ts:
        rem_sec = int(lock_info.get("locked_until", 0) - now_ts)
        rem_min = max(1, rem_sec // 60)
        return f"""<span id="active-email-pill" class="active-pill font-mono locked-manual" title="人工保护中: {active_email} (剩余{rem_min}分，点击复制)" onclick="copyText('{active_email}')"{oob_attr}>
            {shield_svg}<span class="active-email-val" data-active-email="{short_name}">{short_name}</span>{tier_badge_inline}<span class="lock-tag font-mono">{rem_min}m</span>
            <button class="btn-unlock-pill font-mono" onclick="doUnlockProtection(); event.preventDefault(); event.stopPropagation();" title="恢复自动轮转">✕</button>
        </span>"""
    else:
        return f"""<span id="active-email-pill" class="active-pill font-mono auto-mode" title="当前活跃账号: {active_email} (点击复制)" onclick="copyText('{active_email}')"{oob_attr}>
            {zap_svg}<span class="active-email-val" data-active-email="{short_name}">{short_name}</span>{tier_badge_inline}
        </span>"""


def _format_live_5h_reset_str(raw_iso: str, now_ts: int) -> str:
    """仅格式化仍在有效未来窗口内的 Google 真实 5h 倒计时；已过期或空串返回空串以触发待预热显示"""
    if not raw_iso or raw_iso == "--" or "T" not in str(raw_iso):
        return ""
    t_ts = _parse_iso_to_epoch(str(raw_iso))
    if t_ts <= 0:
        return ""
    diff = t_ts - now_ts
    if diff <= -60 or diff > 18060:
        return ""
    if diff <= 0:
        return "即将恢复"
    return format_reset_time(str(raw_iso))


def _summarize_account_tiers(accounts: Dict[str, Any], active_email: str) -> Tuple[int, int, int, str, str]:
    """汇总三档账号数量并提取当前活跃账号的类别徽标"""
    paid_pro_count = 0
    free_pro_count = 0
    free_count = 0
    active_tier = ""
    active_tier_display = ""
    for em, acc in accounts.items():
        if not isinstance(acc, dict):
            continue
        t_code, t_disp, _, _ = classify_account_tier(acc)
        if t_code == "PAID_PRO":
            paid_pro_count += 1
        elif t_code == "FREE_PRO":
            free_pro_count += 1
        else:
            free_count += 1
        if active_email and em == active_email:
            active_tier = t_code
            active_tier_display = t_disp
    return paid_pro_count, free_pro_count, free_count, active_tier, active_tier_display


def render_table_rows(include_oob: bool = False) -> str:
    data = ENGINE.load_accounts()
    active_email = data.get("active_email", "")
    accounts = data.get("accounts", {})

    total_count = len(accounts)
    paid_cnt, free_pro_cnt, free_cnt, active_tier, active_tier_disp = _summarize_account_tiers(accounts, active_email)
    pro_count = paid_cnt + free_pro_cnt
    avg_g = format_quota_int_pct(sum(a.get("gemini", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count))
    avg_c = format_quota_int_pct(sum(a.get("claude", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count))
    cur_time = time.strftime("%H:%M:%S")

    if not accounts:
        empty_row = '<tr><td colspan="7" style="text-align:center; padding: 24px; font-size:13px; font-weight:900; background:#FFE4E6;">暂无账号，请执行单向导入</td></tr>'
        if include_oob:
            return empty_row + "\n" + render_top_bar_stats_html(0, 0, 0.0, 0.0, cur_time, oob=True) + "\n" + render_active_pill_html("", oob=True) + "\n" + render_rotation_button_html(oob=True) + "\n" + render_version_marker_html(oob=True)
        return empty_row

    rows = []
    now = int(time.time())

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
        is_region_restricted = bool(acc.get("region_restricted"))
        region_change_url = acc.get("region_change_url") or build_region_change_url(email)

        # 四档账号类别与黄金满血 Neon 能力判定
        acc_tier, acc_tier_display, _is_pro, acc_has_5h = classify_account_tier(acc)
        acc_has_neon = detect_account_has_neon(acc)
        tier_rank = 0 if acc_tier == "PAID_PRO" else (1 if acc_tier == "STUDENT_PRO" else (2 if (acc_tier == "FREE_PRO" and acc_has_neon) else (3 if acc_tier == "FREE_PRO" else 4)))
        tier_badge_html = render_tier_badge_html(acc_tier, acc_tier_display, has_neon=acc_has_neon, email=email)

        region_flag_html = (
            f"""<a class="region-flag-cn" href="{region_change_url}" target="_blank" rel="noopener" onclick="event.stopPropagation();" title="关联地区受限 (中国 / UNSUPPORTED_LOCATION)，无法使用 Antigravity。点击前往 Google 地区修改申请页"><svg viewBox="0 0 30 20" width="16" height="11" aria-label="CN"><rect width="30" height="20" fill="#DE2910"/><polygon fill="#FFDE00" points="5,2 5.88,4.71 8.73,4.71 6.43,6.38 7.31,9.09 5,7.42 2.69,9.09 3.57,6.38 1.27,4.71 4.12,4.71"/><polygon fill="#FFDE00" points="10,1.2 10.29,2.1 11.24,2.1 10.47,2.66 10.76,3.56 10,3.0 9.24,3.56 9.53,2.66 8.76,2.1 9.71,2.1"/><polygon fill="#FFDE00" points="12,3.2 12.29,4.1 13.24,4.1 12.47,4.66 12.76,5.56 12,5.0 11.24,5.56 11.53,4.66 10.76,4.1 11.71,4.1"/><polygon fill="#FFDE00" points="12,6.2 12.29,7.1 13.24,7.1 12.47,7.66 12.76,8.56 12,8.0 11.24,8.56 11.53,7.66 10.76,7.1 11.71,7.1"/><polygon fill="#FFDE00" points="10,8.2 10.29,9.1 11.24,9.1 10.47,9.66 10.76,10.56 10,10.0 9.24,10.56 9.53,9.66 8.76,9.1 9.71,9.1"/></svg></a>"""
            if is_region_restricted
            else ""
        )

        if is_active:
            main_btn_html = """<div class="btn-in-use font-mono" title="当前主程序正在使用此账号护航">在用</div>"""
        elif is_region_restricted:
            main_btn_html = f"""<a class="btn btn-region-unlock font-mono"
                            href="{region_change_url}" target="_blank" rel="noopener"
                            onclick="event.stopPropagation();"
                            title="关联地区受限 (中国)，点击前往 Google 地区修改申请页面">解锁</a>"""
        elif is_blocked:
            main_btn_html = f"""<button class="btn btn-unblock font-mono" 
                            onclick="doUnblockAccount('{email}'); event.preventDefault(); event.stopPropagation();"
                            title="在现役 ego lite 浏览器中拉起解封页面并自动定向该账号（后台自动监听解锁）">解封</button>"""
        else:
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

        c_models = acc.get("claude_models") or []
        has_real_55 = any(("5-5" in m or "5.5" in m) for m in c_models) if c_models else (acc.get("claude_version") == "5.5")
        claude_ver = "5.5" if has_real_55 else "4.6"

        # Gemini 配额 (官方统一 Gemini 分组：Pro 双轨 5H+W，FREE 单轨 W)
        g_w = _safe_float(acc.get("gemini", {}).get("quota_weekly", 1.0), 1.0)
        if not acc_has_5h:
            g_5h = None
            g_reset_5h = ""
        else:
            raw_g5h = acc.get("gemini", {}).get("quota_5h")
            g_5h = 0.0 if g_w < 0.005 else _safe_float(raw_g5h, 1.0)
            g_reset_5h = "" if g_w < 0.005 else _format_live_5h_reset_str(acc.get("gemini", {}).get("reset_time_5h", ""), now)
        g_reset_w = format_reset_time(acc.get("gemini", {}).get("reset_time_weekly", acc.get("gemini", {}).get("reset_time", "")))
        g_cell = render_quota_cell(g_5h, g_w, g_reset_5h, g_reset_w, model_type="gemini", has_5h=acc_has_5h)

        # Claude 配额 (官方统一 Claude 分组：Pro 双轨 5H+W，FREE 单轨 W)
        c_w = _safe_float(acc.get("claude", {}).get("quota_weekly", 1.0), 1.0)
        if not acc_has_5h:
            c_5h = None
            c_reset_5h = ""
        else:
            raw_c5h = acc.get("claude", {}).get("quota_5h")
            c_5h = 0.0 if c_w < 0.005 else _safe_float(raw_c5h, 1.0)
            c_reset_5h = "" if c_w < 0.005 else _format_live_5h_reset_str(acc.get("claude", {}).get("reset_time_5h", ""), now)
        c_reset_w = format_reset_time(acc.get("claude", {}).get("reset_time_weekly", acc.get("claude", {}).get("reset_time", "")))
        c_cell = render_quota_cell(c_5h, c_w, c_reset_5h, c_reset_w, model_type="claude", claude_ver=claude_ver, has_5h=acc_has_5h)

        short_name = email.split("@")[0] if "@" in email else email

        row = f"""
        <tr class="account-row {active_class}" 
            draggable="true"
            style="background-color: {row_bg};"
            data-email="{email}"
            data-orig-idx="{idx}"
            data-tier="{acc_tier}"
            data-tier-rank="{tier_rank}"
            data-claude-ver="{claude_ver}"
            data-gemini-5h="{g_5h if g_5h is not None else -1}"
            data-gemini-w="{g_w}"
            data-claude-5h="{c_5h if c_5h is not None else -1}"
            data-claude-w="{c_w}"
            data-region-restricted="{'1' if is_region_restricted else '0'}"
            data-is-active="{'1' if is_active else '0'}">
            <td class="col-center col-check" style="background-color: {row_bg};"><input type="checkbox" class="row-select-cb neo-checkbox" value="{email}" data-email="{email}" onchange="onRowSelectChange(this)" title="勾选 {email}"></td>
            <td class="col-center font-mono num-col" style="background-color: {row_bg};">{num_html}</td>
            <td class="col-center col-tier" style="background-color: {row_bg};">{tier_badge_html}</td>
            <td class="col-email" style="background-color: {row_bg};">
                <div class="email-cell-inner">
                    <span class="email-text font-mono" onclick="copyText('{email}')" title="点击复制: {email}" data-raw-email="{email}" data-short-name="{short_name}">{short_name}</span>{region_flag_html}
                </div>
            </td>
            <td class="col-quota col-quota-gemini" style="background-color: {row_bg};">{g_cell}</td>
            <td class="col-quota col-quota-claude" style="background-color: {row_bg};">{c_cell}</td>
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
        active_acc_obj = accounts.get(active_email, {}) if active_email else {}
        output += "\n" + render_top_bar_stats_html(total_count, pro_count, avg_g, avg_c, cur_time, oob=True)
        output += "\n" + render_active_pill_html(
            active_email,
            oob=True,
            active_tier=active_tier,
            active_tier_display=active_tier_disp,
            active_has_neon=detect_account_has_neon(active_acc_obj),
        )
        output += "\n" + render_rotation_button_html(oob=True)
        output += "\n" + render_version_marker_html(oob=True)
    return output


def render_version_marker_html(oob: bool = False) -> str:
    oob_attr = ' hx-swap-oob="outerHTML:#hub-version-marker"' if oob else ''
    return f"""<div id="hub-version-marker"{oob_attr} data-version="{__version__}" style="display:none;"></div>"""


def render_rotation_button_html(oob: bool = False) -> str:
    rot_cfg = get_auto_rotation_config()
    mode = rot_cfg.get("mode", "gemini")

    if mode == "gemini":
        btn_cls = "btn-rotation-gemini"
        btn_text = "全局 Gemini"
        btn_icon = '<polygon points="5 3 19 12 5 21 5 3"/>'
        btn_title = "轮转模式: 全局 Gemini (全池参与耗尽自动切号，点击切换为仅付费 PRO 轮转)"
    elif mode == "paid_pro":
        btn_cls = "btn-rotation-claude"
        btn_text = "付费 PRO"
        btn_icon = '<polygon points="5 3 19 12 5 21 5 3"/>'
        btn_title = "轮转模式: 仅付费 PRO (只在付费 PRO 账号间自动轮转，点击关闭自动轮转)"
    else:  # 'off'
        btn_cls = "btn-rotation-off"
        btn_text = "已关闭"
        btn_icon = '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>'
        btn_title = "轮转模式: 已关闭 (看门狗已冻结，点击开启全局 Gemini 轮转)"

    oob_attr = ' hx-swap-oob="outerHTML:#btn-rotation-toggle"' if oob else ''
    return f"""<button id="btn-rotation-toggle"{oob_attr} class="btn btn-top {btn_cls} font-mono"
                        onclick="cycleAutoRotation(this); event.preventDefault(); event.stopPropagation();"
                        data-mode="{mode}"
                        title="{btn_title}">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;">{btn_icon}</svg>
                    {btn_text}
                </button>"""


def render_dashboard_html() -> str:
    data = ENGINE.load_accounts()
    accounts = data.get("accounts", {})
    active_email = data.get("active_email", "")

    total_count = len(accounts)
    paid_pro_count, free_pro_count, free_count, active_tier, active_tier_disp = _summarize_account_tiers(accounts, active_email)
    pro_count = paid_pro_count + free_pro_count
    avg_g = format_quota_int_pct(sum(a.get("gemini", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count))
    avg_c = format_quota_int_pct(sum(a.get("claude", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count))
    cur_time = time.strftime("%H:%M:%S")

    rot_btn_html = render_rotation_button_html(oob=False)
    table_rows = render_table_rows(include_oob=False)
    stats_html = render_top_bar_stats_html(total_count, pro_count, avg_g, avg_c, cur_time, oob=False)
    active_acc_obj = accounts.get(active_email, {}) if active_email else {}
    active_pill_html = render_active_pill_html(
        active_email,
        oob=False,
        active_tier=active_tier,
        active_tier_display=active_tier_disp,
        active_has_neon=detect_account_has_neon(active_acc_obj),
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Antigravity Hub · Neo-Brutalism</title>
    <link rel="icon" type="image/png" sizes="64x64" href="/favicon.png?v={__version__}">
    <link rel="icon" type="image/png" sizes="512x512" href="/logo.png?v={__version__}">
    <link rel="apple-touch-icon" href="/logo.png?v={__version__}">
    <script src="/static/htmx.min.js"></script>
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
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Space Grotesk", sans-serif;
            padding: 6px 0 10px 0;
            margin: 0;
            width: 100%;
            font-size: 12px;
            line-height: 1.2;
            min-width: 924px !important;
            -webkit-font-smoothing: antialiased;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            overflow-x: hidden;
            overflow-y: auto;
        }}

        /* 彻底根除滚动条，绝不允许 WebKit 垂直滚动条挤压视口 */
        ::-webkit-scrollbar {{
            display: none !important;
            width: 0 !important;
            height: 0 !important;
        }}

        .font-mono {{
            font-family: ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Monaco, Consolas, monospace;
            font-variant-numeric: tabular-nums;
        }}

        /* 🚀 官方超紧凑显瘦版心：自适应 720px 至 960px，默认最小宽度零截断 */
        .app-container {{
            width: 100% !important;
            max-width: 960px !important;
            min-width: 720px !important;
            margin: 0 auto;
            box-sizing: border-box;
            padding: 0 4px;
            flex-shrink: 0;
            display: flex;
            flex-direction: column;
            gap: 6px;
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

        /* 顶栏控制条：新野兽派高饱和柠檬黄底 + 2.5px 纯黑粗框 + 4px 硬投影 + 10px 微圆角 */
        .top-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border: var(--border-thick);
            border-radius: var(--radius-card);
            background: var(--yellow-main);
            padding: 5px 8px;
            box-shadow: var(--shadow-hard);
            margin-bottom: 6px;
            width: 100% !important;
            box-sizing: border-box;
            white-space: nowrap !important;
            gap: 6px;
        }}

        .top-left {{
            display: inline-flex;
            align-items: center;
            flex-shrink: 0;
            gap: 4px;
        }}

        .top-center {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }}

        .top-right {{
            display: inline-flex;
            align-items: center;
            justify-content: flex-end;
            flex-shrink: 0;
            margin-left: auto;
            gap: 4px;
        }}

        .brand-logo-wrap {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            height: 32px;
            text-decoration: none;
            cursor: pointer;
            flex-shrink: 0;
            padding: 0 4px;
            transition: transform 0.1s ease;
        }}
        .brand-logo-wrap:hover {{
            transform: scale(1.06);
        }}
        .brand-logo-img {{
            height: 30px;
            width: auto;
            display: block;
            object-fit: contain;
        }}
        .brand-title {{
            background: #00F0FF;
            color: #000000;
            font-size: 11.5px;
            font-weight: 900;
            letter-spacing: 0.5px;
            padding: 0 8px;
            height: 28px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            white-space: nowrap !important;
            flex-shrink: 0 !important;
            box-sizing: border-box;
            user-select: none;
        }}
        .active-pill {{
            background: #DCFCE7 !important;
            color: #000000 !important;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            padding: 0 9px;
            height: 28px;
            min-width: auto !important;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            font-size: 11px;
            font-weight: 900;
            box-shadow: 2px 2px 0px #000000;
            white-space: nowrap !important;
            flex-shrink: 0 !important;
            cursor: pointer;
            box-sizing: border-box;
            transition: all 0.08s ease;
        }}
        .active-pill:hover {{
            background: #BBF7D0 !important;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .active-pill.locked-manual {{
            background: #FFE4E6 !important;
            border-color: #E11D48 !important;
            color: #9F1239 !important;
        }}
        .active-pill.locked-manual:hover {{
            background: #FECDD3 !important;
        }}
        .active-tier-tag {{
            font-size: 9px;
            font-weight: 900;
            padding: 0 4px;
            height: 16px;
            display: inline-flex;
            align-items: center;
            border: 1.5px solid #000000;
            border-radius: 3px;
            line-height: 1;
            flex-shrink: 0;
        }}
        .active-tier-paid {{ background: #FEF3C7; color: #B45309; }}
        .active-tier-freepro {{ background: #E0F2FE; color: #0369A1; }}
        .active-tier-free {{ background: #F3F4F6; color: #4B5563; }}
        .version-badge {{
            background: #FEF08A;
            color: #713F12;
            border: 1.5px solid #000000;
            border-radius: var(--radius-btn);
            padding: 0 5px;
            height: 20px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 9.5px;
            font-weight: 900;
            box-shadow: 1px 1px 0px #000000;
            white-space: nowrap !important;
            flex-shrink: 0 !important;
            user-select: none;
            letter-spacing: -0.2px;
            margin-left: 3px;
        }}
        .lock-tag {{
            font-size: 10px;
            color: #E11D48;
            font-weight: 900;
        }}
        .auto-tag {{
            display: none;
        }}
        .btn-unlock-pill {{
            margin-left: 4px;
            background: #E11D48;
            color: #FFFFFF;
            border: 1.5px solid #000000;
            border-radius: 3px;
            padding: 0 4px;
            font-size: 9.5px;
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
            padding: 0 5px;
            height: 26px;
            font-size: 11px;
            font-weight: 900;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 2.5px;
            cursor: pointer;
            box-sizing: border-box;
            transition: all 0.08s ease;
        }}
        .btn-top:hover {{
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .btn-top:active {{
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000000;
        }}
        .btn-import {{ background: #00F0FF; color: #000000; }}
        .btn-export {{ background: #FFE600; color: #000000; }}
        .btn-refresh-all {{ background: #22C55E; color: #000000; }}
        .btn-mask {{
            background: #F1F5F9;
            color: #000000;
            font-weight: 900;
            border: 2px solid #000000;
            box-shadow: 2px 2px 0px #000000;
            padding: 0 7px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 2px;
        }}
        .btn-mask:hover {{
            background: #E2E8F0;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .btn-mask.active {{
            background: #FFE600;
            color: #000000;
            font-weight: 900;
            border: 2px solid #000000;
            box-shadow: 2px 2px 0px #000000;
        }}
        .btn-mask.active:hover {{
            background: #FACC15;
        }}
        .btn-settings {{ background: #F1F5F9; color: #000000; font-weight: 900; }}
        .btn-settings:hover {{ background: #E2E8F0; }}
        .btn-rotation-gemini {{ background: #4ADE80; color: #000000; font-weight: 900; }}
        .btn-rotation-gemini:hover {{ background: #22C55E; }}
        .btn-rotation-claude {{ background: #F59E0B; color: #000000; font-weight: 900; }}
        .btn-rotation-claude:hover {{ background: #D97706; }}
        .btn-rotation-off {{ background: #E2E8F0; color: #000000; font-weight: 900; }}
        .btn-rotation-off:hover {{ background: #CBD5E1; }}
        /* 向后兼容 */
        .btn-rotation-on {{ background: #4ADE80; color: #000000; font-weight: 900; }}

        .control-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #FFFFFF;
            border: var(--border-thick);
            border-radius: var(--radius-card);
            box-shadow: var(--shadow-hard);
            padding: 5px 7px;
            margin-bottom: 6px;
            width: 100% !important;
            box-sizing: border-box;
            gap: 4px;
            flex-wrap: nowrap !important;
            white-space: nowrap !important;
        }}
        .control-left-group {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            flex-shrink: 0;
        }}
        .search-box {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: #F4F0EA;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            padding: 0 6px;
            height: 26px;
            width: 108px;
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
            font-size: 9.5px;
            font-weight: 900;
            background: #E5E7EB;
            color: #4B5563;
            border: 1px solid #9CA3AF;
            border-radius: 3px;
            padding: 0 3px;
            line-height: 13px;
            height: 13px;
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
            gap: 4px;
            flex-shrink: 0;
        }}
        .filter-divider {{
            width: 2px;
            height: 18px;
            background: #CBD5E1;
            flex-shrink: 0;
            margin: 0 1px;
        }}
        .filter-tab {{
            background: #F4F0EA;
            color: #000000;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            font-size: 10px;
            font-weight: 900;
            padding: 0 6px;
            height: 26px;
            flex-shrink: 0;
            cursor: pointer;
            box-sizing: border-box;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 3px;
            transition: all 0.08s ease;
        }}
        .tier-tab[data-tier-filter="PAID_PRO"].active {{ background: #FEF3C7; color: #B45309; }}
        .tier-tab[data-tier-filter="FREE_PRO"].active {{ background: #E0F2FE; color: #0369A1; }}
        .tier-tab[data-tier-filter="FREE"].active {{ background: #E5E7EB; color: #1F2937; }}
        .dot-amber {{ background: #F59E0B; }}
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
            font-size: 9.5px;
            opacity: 0.95;
            font-weight: 800;
        }}
        .filter-dot {{
            width: 7px;
            height: 7px;
            border-radius: 50%;
            border: 1.5px solid #000000;
            display: inline-block;
            margin-right: 2px;
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
            font-size: 10.5px;
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

        /* 表格总容器：3px 纯黑外边框 + 4px 硬投影 + 10px 微圆角 + 永远固定 15 行高度（少于 15 个留白，超 15 行自动显现同风格右侧滚动条） */
        .table-wrap {{
            border: var(--border-thick);
            background: #FFFFFF;
            box-shadow: var(--shadow-hard);
            border-radius: var(--radius-card);
            overflow-x: hidden;
            overflow-y: auto;
            height: calc(15 * 40px + 34px);
            min-height: calc(15 * 40px + 34px);
            max-height: calc(15 * 40px + 34px);
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box;
            scrollbar-width: thin;
            scrollbar-color: #111827 #F8FAFC;
        }}
        .table-wrap::-webkit-scrollbar {{
            width: 8px;
        }}
        .table-wrap::-webkit-scrollbar-track {{
            background: #F8FAFC;
            border-left: 2px solid #000000;
        }}
        .table-wrap::-webkit-scrollbar-thumb {{
            background: #111827;
            border-left: 1px solid #000000;
        }}
        .table-wrap::-webkit-scrollbar-thumb:hover {{
            background: #F59E0B;
        }}
        .region-flag-cn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            margin-left: 4px;
            padding: 1px;
            background: #DE2910;
            border: 1.5px solid #991B1B;
            line-height: 0;
            text-decoration: none;
            box-shadow: 1px 1px 0px #000000;
        }}
        .btn-region-unlock {{
            width: 54px !important;
            min-width: 54px !important;
            max-width: 54px !important;
            height: 22px !important;
            flex-shrink: 0 !important;
            background: #FEE2E2;
            color: #B91C1C !important;
            font-size: 10.5px;
            font-weight: 900;
            border: 2px solid #991B1B;
            border-radius: 4px;
            box-shadow: 2px 2px 0px #000000;
            padding: 0 !important;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            cursor: pointer;
        }}
        .btn-region-unlock:hover {{
            background: #FECACA;
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
            padding: 6px 4px;
            font-size: 10.5px;
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
        .th-tier {{ background: #FBBF24; text-align: center; }}
        .th-email {{ background: #FDE047; text-align: left; padding-left: 6px; }}
        .th-gemini {{ background: #7DD3FC; text-align: center; }}
        .th-claude {{ background: #FB923C; text-align: center; }}
        .th-action {{ background: #4ADE80; text-align: center; }}

        /* 🔀 Gemini / Claude 表头三态循环排序交互与角标 */
        .th-sortable {{
            cursor: pointer;
            user-select: none;
            transition: filter 0.12s ease;
        }}
        .th-sortable:hover {{
            filter: brightness(0.92);
        }}
        .th-sortable:active {{
            filter: brightness(0.85);
        }}
        .th-sort-inner {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
            width: 100%;
            box-sizing: border-box;
        }}
        .sort-badge {{
            display: inline-flex;
            align-items: center;
            background: #FFFFFF;
            color: #000000;
            font-size: 9px;
            font-weight: 900;
            padding: 0 4px;
            height: 16px;
            line-height: 16px;
            border: 1px solid #000000;
            border-radius: 3px;
            box-shadow: 1px 1px 0px #000000;
            letter-spacing: 0;
            white-space: nowrap;
        }}

        tbody tr {{
            height: 34px;
        }}

        /* 所有单元格：实线 2px 纯黑分割网格，严格统一 box-sizing */
        tbody td {{
            padding: 3px 4px;
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
            width: 70px !important;
            min-width: 70px !important;
            max-width: 70px !important;
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

        /* 状态徽章：严格定宽 58px × 21px + 1.5px 描边与投影，安全呼吸空间，零边框重叠 */
        .badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 58px;
            height: 20px;
            font-size: 9px;
            font-weight: 900;
            border: 1.5px solid #000000;
            border-radius: var(--radius-pill);
            box-shadow: 1.5px 1.5px 0px #000000;
            line-height: 1;
            letter-spacing: 0.2px;
            box-sizing: border-box;
            gap: 2px;
            white-space: nowrap !important;
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

        /* 账号邮箱与 PRO 徽章紧凑贴合 (左内边距 6px 远离分隔线，紧跟名字 5px 间隙，彻底消灭右侧大空白) */
        .col-email {{
            padding: 0 6px !important;
            white-space: nowrap !important;
            box-sizing: border-box;
            overflow: hidden;
            vertical-align: middle;
        }}
        .email-cell-inner {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            vertical-align: middle;
        }}
        .email-text {{
            font-size: 11.5px;
            font-weight: 900;
            display: inline-block;
            color: #000000;
            vertical-align: middle;
            white-space: nowrap !important;
            cursor: pointer;
            padding: 1px 2px;
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
            width: 28px !important;
            min-width: 28px !important;
            max-width: 28px !important;
            height: 17px;
            border: 1.5px solid #000000;
            border-radius: 3px;
            box-shadow: 1.5px 1.5px 0px #000000;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            flex-shrink: 0 !important;
            white-space: nowrap !important;
            text-align: center;
            line-height: 1;
            padding: 0 !important;
            letter-spacing: 0px;
        }}
        .pro-tag-55 {{
            background: #F59E0B !important;
            color: #000000 !important;
            box-shadow: 1.5px 1.5px 0px #000000 !important;
        }}
        .pro-tag-46 {{
            background: var(--pink-accent) !important;
            color: #FFFFFF !important;
            box-shadow: 1.5px 1.5px 0px #000000 !important;
        }}

        /* 配额单元格：三轨绝对对齐 (自适应 924px~1034px 零截断) */
        .col-quota {{
            padding: 2px 4px !important;
            box-sizing: border-box;
            overflow: hidden;
            text-align: center;
            vertical-align: middle;
        }}
        .col-quota-g4 {{
            min-width: 162px;
        }}
        .col-quota-g38 {{
            min-width: 152px;
        }}
        .col-quota-gemini {{
            min-width: 152px;
        }}
        .col-quota-claude {{
            min-width: 152px;
        }}
        .tag-w-g4 {{ background: #A855F7; color: #FFFFFF; }}
        .q-cell-empty {{
            min-height: 22px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .q-empty-dash {{
            font-size: 13px;
            font-weight: 900;
            color: #94A3B8;
            opacity: 0.75;
            user-select: none;
        }}
        .q-cell {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2.5px;
            width: 100%;
            box-sizing: border-box;
        }}
        .q-row {{
            display: flex;
            align-items: center;
            justify-content: center; /* 核心：水平绝对居中，彻底消灭右侧大空洞 */
            gap: 4px;
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

        /* 进度条：超紧凑 34px 至 64px，兼容 720px 极窄窗口与宽屏自适应 */
        .q-track {{
            flex: 1 1 42px !important;
            min-width: 34px !important;
            max-width: 64px !important;
            height: 8px;
            background: #FFFFFF;
            border: 1.5px solid #000000;
            border-radius: var(--radius-pill);
            box-shadow: 1px 1px 0px #000000;
            overflow: hidden;
            box-sizing: border-box;
        }}
        .q-fill {{ height: 100%; transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1); }}
        
        /* 百分比数值：严格定宽 32px（整数取整极简态），居右对齐，等宽防抖 */
        .q-val {{
            width: 32px !important;
            min-width: 32px !important;
            max-width: 32px !important;
            flex-shrink: 0 !important;
            text-align: right;
            font-weight: 900;
            font-size: 10.5px;
            box-sizing: border-box;
            white-space: nowrap !important;
        }}

        /* 50px 固定重置时间槽 */
        .q-slot {{
            width: 50px !important;
            min-width: 50px !important;
            max-width: 50px !important;
            flex-shrink: 0 !important;
            display: inline-flex;
            justify-content: center;
            align-items: center;
            box-sizing: border-box;
        }}
        .q-reset {{
            width: 48px !important;
            min-width: 48px !important;
            max-width: 48px !important;
            flex-shrink: 0 !important;
            font-size: 9px;
            font-weight: 900;
            padding: 1.5px 0;
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

        /* 操作按钮容器与定宽按键 (无每行预热按钮，紧凑 86px) */
        .col-actions {{
            width: 86px !important;
            min-width: 86px !important;
            max-width: 86px !important;
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
        
        /* 切换按键与在用徽章：严格定宽 54px × 22px，圆角 4px，手感充沛紧凑 */
        .btn-switch {{ 
            width: 54px !important; 
            min-width: 54px !important; 
            max-width: 54px !important; 
            height: 22px !important;
            flex-shrink: 0 !important; 
            background: var(--cyan-accent); 
            color: #000000; 
            font-size: 10.5px;
            font-weight: 900;
            border: 2px solid #000000;
            border-radius: 4px;
            box-shadow: 2px 2px 0px #000000;
            padding: 0 !important;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }}
        
        .btn-warmup {{ 
            width: 38px !important; 
            min-width: 38px !important; 
            max-width: 38px !important; 
            height: 22px !important;
            flex-shrink: 0 !important; 
            background: #FB923C; 
            color: #000000; 
            font-size: 10.5px;
            font-weight: 900;
            border: 2px solid #000000;
            border-radius: 4px;
            box-shadow: 2px 2px 0px #000000;
            padding: 0 !important;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
        }}
        .btn-warmup:hover {{
            background: #EA580C;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .btn-warmup:active {{
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000000;
        }}

        .btn-in-use {{
            width: 54px !important;
            min-width: 54px !important;
            max-width: 54px !important;
            height: 22px !important;
            background: #8bcbb1 !important;
            color: #0a1713 !important;
            font-size: 10.5px !important;
            font-weight: 900 !important;
            border: 2px solid #000000 !important;
            border-radius: 4px !important;
            box-shadow: 2px 2px 0px #000000 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            letter-spacing: 0.5px !important;
            cursor: default !important;
            user-select: none !important;
            box-sizing: border-box !important;
            padding: 0 !important;
            flex-shrink: 0 !important;
        }}

        .btn-unblock {{ 
            width: 54px !important; 
            min-width: 54px !important; 
            max-width: 54px !important; 
            height: 22px;
            flex-shrink: 0 !important; 
            background: #FF4B4B; 
            color: #FFFFFF; 
            font-size: 10.5px;
            font-weight: 900;
            border: 2px solid #000000;
            border-radius: 4px;
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

        .btn-in-use,
        .active-badge-action {{
            width: 54px !important;
            min-width: 54px !important;
            max-width: 54px !important;
            height: 22px !important;
            background: #8bcbb1 !important;
            color: #0a1713 !important;
            font-size: 10.5px !important;
            font-weight: 900 !important;
            border: 2px solid #000000 !important;
            border-radius: var(--radius-btn) !important;
            box-shadow: 2px 2px 0px #000000 !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            letter-spacing: 0.5px !important;
            cursor: default !important;
            user-select: none !important;
            box-sizing: border-box !important;
            padding: 0 !important;
            flex-shrink: 0 !important;
        }}

        /* 🔲 Neo-Brutalism 复选框与批量控制 */
        .th-check, .col-check {{
            width: 28px !important;
            min-width: 28px !important;
            max-width: 28px !important;
            text-align: center !important;
            padding: 0 !important;
            vertical-align: middle !important;
            box-sizing: border-box !important;
        }}
        .neo-checkbox {{
            appearance: none;
            -webkit-appearance: none;
            width: 15px;
            height: 15px;
            border: 2px solid #000000;
            border-radius: 3px;
            background: #FFFFFF;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            vertical-align: middle;
            transition: all 0.05s ease;
            box-shadow: 1px 1px 0px #000000;
            margin: 0;
            padding: 0;
            flex-shrink: 0;
        }}
        .neo-checkbox:hover {{
            transform: translate(-0.5px, -0.5px);
            box-shadow: 2px 2px 0px #000000;
            background: #FFDE59;
        }}
        .neo-checkbox:checked {{
            background-color: #10B981;
            background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 16 16' fill='white' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M12.207 4.793a1 1 0 010 1.414l-5 5a1 1 0 01-1.414 0l-2-2a1 1 0 011.414-1.414L6.5 9.086l4.293-4.293a1 1 0 011.414 0z'/%3E%3C/svg%3E");
            background-position: center;
            background-repeat: no-repeat;
            background-size: 13px;
        }}
        .neo-checkbox:indeterminate {{
            background-color: #3B82F6;
            background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 16 16' fill='white' xmlns='http://www.w3.org/2000/svg'%3E%3Crect x='3' y='7' width='10' height='2' rx='1'/%3E%3C/svg%3E");
            background-position: center;
            background-repeat: no-repeat;
        }}
        tr.is-row-selected {{
            background-color: #FEF08A !important;
            outline: 2px solid #000000;
            outline-offset: -2px;
        }}
        tr.is-row-selected td {{
            background-color: #FEF08A !important;
        }}

        /* 🎛️ 批量操作指示卡片 */
        .batch-bar {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            background: #FFE600;
            border: 2px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 2px 2px 0px #000000;
            padding: 0 8px;
            height: 26px;
            font-size: 11px;
            font-weight: 900;
            color: #000000;
            box-sizing: border-box;
            margin-left: auto;
        }}
        .batch-count-label {{
            font-size: 10.5px;
            margin-right: 2px;
            white-space: nowrap;
        }}
        .btn-batch {{
            height: 20px;
            padding: 0 6px;
            font-size: 10px;
            font-weight: 900;
            border: 1.5px solid #000000;
            border-radius: 3px;
            cursor: pointer;
            box-shadow: 1px 1px 0px #000000;
            display: inline-flex;
            align-items: center;
            gap: 2px;
            box-sizing: border-box;
            transition: all 0.05s ease;
            white-space: nowrap;
        }}
        .btn-batch:hover {{
            transform: translate(-0.5px, -0.5px);
            box-shadow: 1.5px 1.5px 0px #000000;
        }}
        .btn-batch:active {{
            transform: translate(0.5px, 0.5px);
            box-shadow: 0px 0px 0px #000000;
        }}
        .btn-batch-export {{
            background: #FFFFFF;
            color: #000000;
        }}
        .btn-batch-export:hover {{
            background: var(--cyan-accent);
        }}
        .btn-batch-delete {{
            background: #FF4B4B;
            color: #FFFFFF;
        }}
        .btn-batch-delete:hover {{
            background: #DC2626;
        }}
        .btn-batch-clear {{
            background: #FFFFFF;
            color: #000000;
            border: 1.5px solid #000000;
            padding: 0 5px;
        }}
        .btn-batch-clear:hover {{
            background: #F4F0EA;
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

        /* Magpie 高密显瘦与显示密度 */
        .density-compact .account-row {{ height: 32px !important; }}
        .density-compact .q-cell {{ padding: 0 !important; }}
        .density-standard .account-row {{ height: 36px !important; }}
        .density-relaxed .account-row {{ height: 42px !important; }}

        /* Magpie 风格 Neo-Brutalism 设置弹窗 */
        .settings-modal-box {{
            background: #F4F0EA;
            width: 500px;
            max-width: 92vw;
            border: 3px solid #000000;
            border-radius: var(--radius-modal);
            box-shadow: 6px 6px 0px #000000;
            animation: popIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .settings-tabs {{
            display: flex;
            background: #EBE6DC;
            border-bottom: 2px solid #000000;
            padding: 0 4px;
            gap: 2px;
        }}
        .settings-tab-btn {{
            padding: 8px 12px;
            font-size: 11px;
            font-weight: 900;
            border: none;
            border-bottom: 2.5px solid transparent;
            background: transparent;
            cursor: pointer;
            color: #4B5563;
            transition: all 0.08s ease;
        }}
        .settings-tab-btn.active {{
            color: #000000;
            border-bottom-color: #000000;
            background: #F4F0EA;
        }}
        .settings-body {{
            padding: 14px 16px;
            min-height: 200px;
            background: #F4F0EA;
        }}
        .cfg-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 11px;
            font-size: 12px;
        }}
        .cfg-label {{
            font-weight: 800;
            color: #111827;
            width: 140px;
            flex-shrink: 0;
        }}
        .cfg-field {{
            flex: 1;
            display: flex;
            justify-content: flex-end;
        }}
        .neo-select {{
            background: #FFFFFF;
            border: 2px solid #000000;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
            box-shadow: 2px 2px 0px #000000;
            outline: none;
            cursor: pointer;
            max-width: 250px;
        }}
        .neo-kbd {{
            background: #FFFFFF;
            color: #000000;
            border: 1px solid #000000;
            box-shadow: 1px 1px 0px #000000;
            padding: 1px 5px;
            border-radius: 3px;
            font-weight: 900;
            font-size: 10px;
        }}
        .settings-footer {{
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            padding: 10px 16px;
            background: #EBE6DC;
            border-top: 2px solid #000000;
        }}
        .btn-settings-save {{
            background: #22C55E;
            color: #000000;
            border: 2px solid #000000;
            border-radius: 4px;
            padding: 0 14px;
            height: 28px;
            font-size: 11px;
            font-weight: 900;
            box-shadow: 2px 2px 0px #000000;
            cursor: pointer;
        }}
        .btn-settings-save:hover {{
            background: #16A34A;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .btn-settings-cancel {{
            background: #FFFFFF;
            color: #000000;
            border: 2px solid #000000;
            border-radius: 4px;
            padding: 0 12px;
            height: 28px;
            font-size: 11px;
            font-weight: 800;
            box-shadow: 2px 2px 0px #000000;
            cursor: pointer;
        }}
        .toggle-wrap {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            font-size: 11px;
            font-weight: 700;
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
        /* 新野兽派底部分页控制栏 (紧随表格底边，margin-top: 6px，彻底消除空洞) */
        .pagination-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: #FFFFFF;
            border: var(--border-thick);
            border-radius: var(--radius-card);
            box-shadow: var(--shadow-hard);
            padding: 3px 10px;
            margin-top: 6px;
            width: 100% !important;
            min-width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box;
            height: 30px;
        }}
        .page-info {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 10.5px;
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
            gap: 6px;
        }}
        .btn-page {{
            background: #F4F0EA;
            color: #000000;
            border: 1.5px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 1.5px 1.5px 0px #000000;
            font-size: 10px;
            font-weight: 900;
            padding: 0 8px;
            height: 22px;
            cursor: pointer;
            box-sizing: border-box;
            transition: all 0.08s ease;
        }}
        .btn-page:hover:not(:disabled) {{
            background: #FFE600;
            transform: translate(-1px, -1px);
            box-shadow: 2.5px 2.5px 0px #000000;
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
            border: 1px solid #D1D5DB;
            color: #9CA3AF;
        }}
    </style>
</head>
<body data-hub-version="{__version__}">
    <div id="hub-version-marker" data-version="{__version__}" style="display:none;"></div>
    <div id="loading-bar"></div>
    <div id="toast" class="toast font-mono"></div>

    <div class="app-container">
        <!-- 新野兽派顶栏控制条 (纯净自解释 + 按钮零截断) -->
        <div class="top-bar">
            <div class="top-left">
                <a href="/" class="brand-logo-wrap" title="Antigravity Hub v{__version__}">
                    <img src="/logo.png?v={__version__}" class="brand-logo-img" alt="Antigravity Hub">
                </a>
                {active_pill_html}
                <span class="version-badge font-mono" title="Antigravity Hub v{__version__}">v{__version__}</span>
            </div>
            {stats_html}
            <div class="top-right">
                <button class="btn btn-top btn-mask font-mono" id="btn-mask-toggle"
                        onclick="toggleAccountMask(); event.preventDefault(); event.stopPropagation();"
                        title="按一下打码，再按一下明文 (快捷键: M)">
                    <span id="btn-mask-icon" style="display:inline-flex; align-items:center;"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:2px;"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg></span><span id="btn-mask-text">打码</span>
                </button>
                <button class="btn btn-top btn-settings font-mono"
                        onclick="openSettingsModal(); event.preventDefault(); event.stopPropagation();"
                        title="控制台设置与预热开关 (快捷键: S)">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:1px;"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                    设置
                </button>
                {rot_btn_html}
                <button class="btn btn-top btn-refresh-all font-mono"
                        onclick="doRefreshQuota(this); event.preventDefault(); event.stopPropagation();"
                        title="立即并发刷新最新配额 (快捷键: R)">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:2px;"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
                    刷新
                </button>
                <button class="btn btn-top btn-import font-mono"
                        onclick="openImportModal(); event.preventDefault(); event.stopPropagation();"
                        title="导入账号备份、批量添加或从 IDE 钥匙串一键吸纳">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:2px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                    导入
                </button>
                <button class="btn btn-top btn-export font-mono"
                        onclick="doExportAccounts(); event.preventDefault(); event.stopPropagation();"
                        title="导出全池账号备份 JSON">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:2px;"><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                    导出
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
                <button class="filter-tab" data-filter="usable" onclick="setFilter('usable', this)"><span class="filter-dot dot-blue"></span>可用</button>
                <button class="filter-tab" data-filter="healthy" onclick="setFilter('healthy', this)"><span class="filter-dot dot-green"></span>充足</button>
                <button class="filter-tab" data-filter="warning" onclick="setFilter('warning', this)"><span class="filter-dot dot-red"></span>告急</button>
                <button class="filter-tab" data-filter="exhausted" onclick="setFilter('exhausted', this)"><span class="filter-dot dot-gray"></span>枯竭</button>
                <span class="filter-divider" aria-hidden="true"></span>
                <button class="filter-tab tier-tab" data-tier-filter="PAID_PRO" onclick="toggleTierFilter('PAID_PRO', this)" title="筛选付费 PRO 账号"><span class="filter-dot dot-amber"></span>付费 PRO</button>
                <button class="filter-tab tier-tab" data-tier-filter="STUDENT_PRO" onclick="toggleTierFilter('STUDENT_PRO', this)" title="筛选学生 PRO 账号"><span class="filter-dot dot-amber"></span>学生 PRO</button>
                <button class="filter-tab tier-tab" data-tier-filter="FREE_PRO" onclick="toggleTierFilter('FREE_PRO', this)" title="筛选免费 PRO 账号"><span class="filter-dot dot-blue"></span>免费 PRO</button>
                <button class="filter-tab tier-tab" data-tier-filter="FREE" onclick="toggleTierFilter('FREE', this)" title="筛选 FREE 账号"><span class="filter-dot dot-gray"></span>FREE</button>
            </div>
            <div class="stats-counter" id="filter-counter">
                <b>{total_count}</b> / {total_count}
            </div>
            <div id="batch-action-bar" class="batch-bar font-mono" style="display:none;">
                <span class="batch-count-label">已选 <b id="batch-selected-count">0</b> 项</span>
                <button type="button" class="btn-batch btn-batch-export font-mono" onclick="doBatchExport()" title="导出所选 JSON">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>导出
                </button>
                <button type="button" class="btn-batch btn-batch-delete font-mono" onclick="doBatchDelete()" title="批量删除所选">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>删除
                </button>
                <button type="button" class="btn-batch btn-batch-clear font-mono" onclick="clearAllSelections()" title="清空全部勾选">取消</button>
            </div>
        </div>

        <!-- 官方规范级超紧凑新野兽表格 (720px 最小宽零截断，移除冗余状态列) -->
        <div class="table-wrap">
            <table>
                <colgroup>
                    <col style="width: 26px;">   <!-- 批量勾选复选框 -->
                    <col style="width: 28px;">   <!-- # 序号+拖拽手柄 -->
                    <col style="width: 76px;">   <!-- 账号类别 (付费 PRO / 免费 PRO / FREE) -->
                    <col style="width: 112px;">  <!-- 账号 -->
                    <col style="width: 29%;">    <!-- Gemini 官方配额 -->
                    <col style="width: 29%;">    <!-- Claude 官方配额 -->
                    <col style="width: 86px;">   <!-- 操作 -->
                </colgroup>
                <thead>
                    <tr>
                        <th class="col-center th-check" title="全选 / 反选"><input type="checkbox" id="master-select-cb" class="neo-checkbox" onchange="toggleMasterSelect(this)"></th>
                        <th class="col-center th-num">#</th>
                        <th class="col-center th-tier th-sortable" onclick="cycleTierSort()" title="点击按账号类别排序">
                            <div class="th-sort-inner">
                                <span>类别</span>
                                <span id="sort-tier-badge" class="sort-badge font-mono" style="display:none;"></span>
                            </div>
                        </th>
                        <th class="th-email">账号</th>
                        <th class="th-gemini th-sortable" onclick="cycleGeminiSort()" title="点击排序 Gemini 额度">
                            <div class="th-sort-inner">
                                <span>Gemini</span>
                                <span id="sort-gemini-badge" class="sort-badge font-mono" style="display:none;"></span>
                            </div>
                        </th>
                        <th class="th-claude th-sortable" onclick="cycleClaudeSort()" title="点击排序 Claude 额度">
                            <div class="th-sort-inner">
                                <span>Claude</span>
                                <span id="sort-claude-badge" class="sort-badge font-mono" style="display:none;"></span>
                            </div>
                        </th>
                        <th class="col-center th-action">操作</th>
                    </tr>
                </thead>
                <tbody id="account-tbody">
                    {table_rows}
                </tbody>
            </table>
        </div>

        <!-- 新野兽派底部分页控制条 (极简自解释，每页最多 20 项) -->
        <div class="pagination-bar font-mono" id="pagination-bar">
            <div class="page-info">
                <span>20 / 页</span>
                <span class="page-dot">·</span>
                <span id="page-indicator">1 / 1</span>
                <span class="page-dot">·</span>
                <span id="page-total">{total_count} 项</span>
            </div>
            <div class="page-actions">
                <button class="btn btn-page font-mono" id="btn-prev-page" onclick="changePage(-1)" disabled title="上一页">← 上一页</button>
                <button class="btn btn-page font-mono" id="btn-next-page" onclick="changePage(1)" disabled title="下一页">下一页 →</button>
            </div>
        </div>
    </div>

    <!-- 📥 Neo-Brutalism 账号纳管与导入中心模态弹窗 -->

    <!-- ⚙️ Neo-Brutalism Magpie 风格控制台设置模态弹窗 -->
    <div id="settings-modal-backdrop" class="modal-backdrop font-mono" onclick="if(event.target===this)closeSettingsModal()">
        <div class="settings-modal-box">
            <div class="modal-header">
                <div style="display:flex; align-items:center; gap:6px;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                    <span>控制台设置</span>
                </div>
                <span class="modal-close" onclick="closeSettingsModal()" title="关闭窗口 (Esc)">✕</span>
            </div>

            <div class="settings-tabs">
                <button class="settings-tab-btn active" id="tab-btn-cfg-gemini" onclick="switchSettingsTab('gemini')">Gemini 专精</button>
                <button class="settings-tab-btn" id="tab-btn-cfg-warmup" onclick="switchSettingsTab('warmup')">错峰预热</button>
                <button class="settings-tab-btn" id="tab-btn-cfg-display" onclick="switchSettingsTab('display')">界面与隐私</button>
                <button class="settings-tab-btn" id="tab-btn-cfg-shortcuts" onclick="switchSettingsTab('shortcuts')">快捷键与集群</button>
            </div>

            <div class="settings-body">
                <!-- TAB 1: Gemini 专精优化 -->
                <div id="settings-pane-gemini" class="settings-pane">
                    <div class="cfg-row">
                        <div class="cfg-label">自动轮换模式</div>
                        <div class="cfg-field">
                            <select id="cfg-rot-mode" class="neo-select font-mono">
                                <option value="gemini">全局 Gemini (全池耗尽自动切号)</option>
                                <option value="paid_pro">付费 PRO (仅付费 PRO 账号轮转)</option>
                                <option value="off">关闭自动轮换</option>
                            </select>
                        </div>
                    </div>
                    <div class="cfg-row">
                        <div class="cfg-label">Gemini 切号触发水位</div>
                        <div class="cfg-field">
                            <select id="cfg-gemini-threshold" class="neo-select font-mono">
                                <option value="0">0% (彻底耗尽时切换)</option>
                                <option value="0.05">5% (剩余 5% 提前接力)</option>
                                <option value="0.10">10% (高并发保活)</option>
                                <option value="0.15">15% (安全水位预备)</option>
                            </select>
                        </div>
                    </div>
                    <div class="cfg-row">
                        <div class="cfg-label">默认列表排序</div>
                        <div class="cfg-field">
                            <select id="cfg-default-sort" class="neo-select font-mono">
                                <option value="gemini_5h_desc">Gemini 5h 降序 (最充沛优先)</option>
                                <option value="gemini_w_desc">Gemini 周度降序</option>
                                <option value="claude_5h_desc">Claude 5h 降序</option>
                                <option value="default">默认原始导入顺序</option>
                            </select>
                        </div>
                    </div>
                </div>

                <!-- TAB 2: 错峰预热开关 -->
                <div id="settings-pane-warmup" class="settings-pane" style="display:none;">
                    <div class="cfg-row">
                        <div class="cfg-label">自动随机预热</div>
                        <div class="cfg-field">
                            <label class="toggle-wrap">
                                <input type="checkbox" id="cfg-hourly-warmup" class="neo-checkbox" checked>
                                <span>开启后台随机错峰 1-token 预热 (关闭则暂停自动预热)</span>
                            </label>
                        </div>
                    </div>
                    <div class="cfg-row">
                        <div class="cfg-label">预热目标模型</div>
                        <div class="cfg-field">
                            <select id="cfg-warmup-model" class="neo-select font-mono">
                                <option value="dual">Gemini + Claude (全双桶预热)</option>
                                <option value="gemini_only">仅 Gemini</option>
                            </select>
                        </div>
                    </div>
                    <div class="cfg-row">
                        <div class="cfg-label">错峰打散窗口</div>
                        <div class="cfg-field">
                            <select id="cfg-warmup-stagger" class="neo-select font-mono">
                                <option value="60">60 秒</option>
                                <option value="120">120 秒</option>
                                <option value="180">180 秒</option>
                            </select>
                        </div>
                    </div>
                </div>

                <!-- TAB 3: 界面与隐私 -->
                <div id="settings-pane-display" class="settings-pane" style="display:none;">
                    <div class="cfg-row">
                        <div class="cfg-label">账号脱敏打码</div>
                        <div class="cfg-field">
                            <label class="toggle-wrap">
                                <input type="checkbox" id="cfg-mask-default" class="neo-checkbox" onchange="toggleAccountMaskFromSettings(this)">
                                <span>开启账号隐私打码 (截图分享保护)</span>
                            </label>
                        </div>
                    </div>
                    <div class="cfg-row">
                        <div class="cfg-label">表格显示密度</div>
                        <div class="cfg-field">
                            <select id="cfg-table-density" class="neo-select font-mono" onchange="onDensityChange(this.value)">
                                <option value="compact">Magpie 极简高密 (32px)</option>
                                <option value="standard" selected>标准高密 (36px)</option>
                                <option value="relaxed">舒适宽松 (42px)</option>
                            </select>
                        </div>
                    </div>
                    <div class="cfg-row">
                        <div class="cfg-label">状态同步频率</div>
                        <div class="cfg-field">
                            <select id="cfg-refresh-sec" class="neo-select font-mono" onchange="onRefreshSecChange(this.value)">
                                <option value="3">3 秒 (极速响应)</option>
                                <option value="5" selected>5 秒 (标准推荐)</option>
                                <option value="10">10 秒 (低频节能)</option>
                                <option value="0">关闭自动同步 (仅手动)</option>
                            </select>
                        </div>
                    </div>
                    <div class="cfg-row">
                        <div class="cfg-label">隐藏已枯竭账号</div>
                        <div class="cfg-field">
                            <label class="toggle-wrap">
                                <input type="checkbox" id="cfg-hide-exhausted" class="neo-checkbox" onchange="onHideExhaustedChange(this)">
                                <span>自动过滤隐藏周额度为 0 的账号</span>
                            </label>
                        </div>
                    </div>
                </div>

                <!-- TAB 4: 快捷键与集群 -->
                <div id="settings-pane-shortcuts" class="settings-pane" style="display:none;">
                    <div style="background:#FFFFFF; border:2px solid #000000; border-radius:4px; padding:8px 12px; margin-bottom:12px;">
                        <div style="font-weight:900; margin-bottom:6px; font-size:12px;">⌨️ 全局快捷键速查</div>
                        <table style="width:100%; font-size:11px; border-collapse:collapse;">
                            <tr><td style="padding:3px 0; width:50px;"><kbd class="neo-kbd">S</kbd></td><td>打开 / 关闭控制台设置</td></tr>
                            <tr><td style="padding:3px 0;"><kbd class="neo-kbd">M</kbd></td><td>切换账号脱敏打码</td></tr>
                            <tr><td style="padding:3px 0;"><kbd class="neo-kbd">R</kbd></td><td>并发拉取最新配额数据</td></tr>
                            <tr><td style="padding:3px 0;"><kbd class="neo-kbd">Esc</kbd></td><td>快速关闭所有弹窗</td></tr>
                        </table>
                    </div>
                    <div style="background:#FFFFFF; border:2px solid #000000; border-radius:4px; padding:8px 12px;">
                        <div style="font-weight:900; margin-bottom:4px; font-size:12px;">🖥️ 本地运行态与账号池概览</div>
                        <div style="font-size:11px; color:#374151;">
                            监听地址: <b class="font-mono">127.0.0.1:{SERVER_PORT}</b> · 账号总数: <b class="font-mono">{total_count}</b> (<b class="font-mono">付费PRO {paid_pro_count}</b> / <b class="font-mono">免费PRO {free_pro_count}</b> / <b class="font-mono">FREE {free_count}</b>)
                        </div>
                    </div>
                </div>
            </div>

            <div class="settings-footer">
                <button class="btn-settings-save font-mono" onclick="saveSettings()">保存应用</button>
                <button class="btn-settings-cancel font-mono" onclick="closeSettingsModal()">关闭</button>
            </div>
        </div>
    </div>

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
                <button class="import-tab-btn active" id="tab-btn-oauth" onclick="switchImportTab('oauth')">Google 授权</button>
                <button class="import-tab-btn" id="tab-btn-sync" onclick="switchImportTab('sync')">IDE 钥匙串吸纳</button>
                <button class="import-tab-btn" id="tab-btn-file" onclick="switchImportTab('file')">JSON 备份导入</button>
            </div>

            <div class="import-body-content">
                <!-- TAB 1: Google OAuth 2.0 浏览器一键授权 (默认首屏) -->
                <div id="import-pane-oauth" class="import-pane">
                    <div style="font-size:12px; font-weight:700; color:#374151; margin-bottom:10px; line-height:1.5;">
                        💡 <b>推荐方式</b>：点击下方【🛡️ 独立容器授权】，将在干净隔离的独立沙盒窗口中打开 Google 登录页。不读取任何旧 Cookie，杜绝串号，支持连续添加多个新账号（如 aicake88、cakeai99 等）。
                    </div>
                    <div style="display:flex; flex-direction:column; gap:10px;">
                        <button class="btn-submit-action font-mono" id="btn-oauth-isolated" onclick="doStartGoogleOAuth(true, this)" style="background:#FFE600; font-weight:900; font-size:13px; height:42px; border:2.5px solid #000000; box-shadow:3px 3px 0px #000000;">
                            🛡️ 独立容器授权 (推荐·全新干净沙盒防串号)
                        </button>
                        <button class="btn-sync-action font-mono" id="btn-oauth-browser" onclick="doStartGoogleOAuth(false, this)" style="background:#FFFFFF; font-size:12px; height:34px;">
                            🌐 默认浏览器授权 (读取当前浏览器会话)
                        </button>
                    </div>
                    <div id="oauth-status-box" style="display:none; margin-top:12px; padding:10px 12px; background:#FEF9C3; border:2px solid #000000; border-radius:6px; box-shadow:2px 2px 0px #000000;">
                        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                            <span id="oauth-status-text" style="font-size:11.5px; font-weight:900; color:#000000;">⏳ 等待授权回调...</span>
                            <button class="btn font-mono" style="background:#FFFFFF; padding:0 8px; height:24px; font-size:10.5px;" onclick="copyCurrentOAuthUrl()">复制链接</button>
                        </div>
                    </div>
                    <div style="margin-top:14px; padding-top:12px; border-top:1.5px dashed #9CA3AF;">
                        <div style="font-size:11.5px; font-weight:700; color:#4B5563; margin-bottom:6px;">手动回调兑换（若网络拦截或需异地粘贴）：</div>
                        <div style="display:flex; gap:8px;">
                            <input type="text" id="oauth-manual-code" class="form-input font-mono" style="margin-bottom:0; flex:1;" placeholder="粘贴回调完整 URL 或 Code">
                            <button class="btn-submit-action font-mono" style="width:90px; height:35px; flex-shrink:0;" onclick="doSubmitManualOAuthCode(this)">解析入库</button>
                        </div>
                    </div>
                </div>

                <!-- TAB 2: 钥匙串一键吸纳 -->
                <div id="import-pane-sync" class="import-pane" style="display:none;">
                    <button class="btn-sync-action font-mono" id="btn-sync-active" onclick="doSyncActiveAccount(this)">
                        ⚡ 立即从 IDE 钥匙串吸纳当前账号
                    </button>
                </div>

                <!-- TAB 3: JSON 备份导入 -->
                <div id="import-pane-file" class="import-pane" style="display:none;">
                    <label class="form-label">选择 JSON 备份文件：</label>
                    <input type="file" id="import-file-input" accept=".json" class="form-input-file" onchange="handleFileUpload(event)">
                    <label class="form-label">或在此直接粘贴 JSON 文本：</label>
                    <textarea id="import-text-input" class="form-textarea font-mono" rows="5" placeholder='[&#10;  {{ "email": "user@gmail.com", "refresh_token": "1//04..." }}&#10;]'></textarea>
                    <button class="btn-submit-action font-mono" onclick="doSubmitJsonImport(this)">
                        📥 解析合并入库
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

        // 🔒 账号脱敏打码 (纯星号掩码 · 零字母零数字 · 防任何猜测)
        let isMasked = localStorage.getItem('hub_account_mask') === '1';

        function maskShortName(name) {{
            if (!name) return '';
            // 彻底切除所有数字和字母，全量替换为纯星号掩码（与字符等长，至少6位）
            const len = Math.max(6, name.length);
            return '*'.repeat(len);
        }}

        const SVG_MASK_EYE_OFF = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:2px;"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
        const SVG_MASK_EYE_ON = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px; margin-right:2px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';

        function applyAccountMask() {{
            const btn = document.getElementById('btn-mask-toggle');
            const maskIcon = document.getElementById('btn-mask-icon');
            const maskText = document.getElementById('btn-mask-text');
            const cfgCb = document.getElementById('cfg-mask-default');
            if (btn) {{
                if (isMasked) {{
                    btn.classList.add('active');
                    if (maskIcon) maskIcon.innerHTML = SVG_MASK_EYE_ON;
                    if (maskText) maskText.innerText = '明文';
                    btn.title = "当前处于打码脱敏状态，按一下显示【明文】(快捷键: M)";
                }} else {{
                    btn.classList.remove('active');
                    if (maskIcon) maskIcon.innerHTML = SVG_MASK_EYE_OFF;
                    if (maskText) maskText.innerText = '打码';
                    btn.title = "当前处于明文状态，按一下进行【打码】脱敏 (快捷键: M)";
                }}
            }}
            if (cfgCb) cfgCb.checked = isMasked;

            // 更新表格每一行的账号文本与防悬停泄密
            document.querySelectorAll('.email-text').forEach(el => {{
                let rawShort = el.getAttribute('data-short-name');
                if (!rawShort) {{
                    rawShort = el.innerText.trim();
                    el.setAttribute('data-short-name', rawShort);
                }}
                let rawEmail = el.getAttribute('data-raw-email') || rawShort;
                if (!el.getAttribute('data-orig-title')) {{
                    el.setAttribute('data-orig-title', el.getAttribute('title') || ('点击复制: ' + rawEmail));
                }}
                if (isMasked) {{
                    el.innerText = maskShortName(rawShort);
                    el.title = "已脱敏 (点击复制凭据)";
                }} else {{
                    el.innerText = rawShort;
                    el.title = el.getAttribute('data-orig-title') || ('点击复制: ' + rawEmail);
                }}
            }});

            // 更新顶栏活跃账号胶囊文本与防悬停泄密
            const activeValEl = document.querySelector('.active-email-val');
            const activePillEl = document.getElementById('active-email-pill');
            if (activeValEl) {{
                let rawActive = activeValEl.getAttribute('data-active-email');
                if (!rawActive) {{
                    rawActive = activeValEl.innerText.trim();
                    activeValEl.setAttribute('data-active-email', rawActive);
                }}
                activeValEl.innerText = isMasked ? maskShortName(rawActive) : rawActive;
            }}
            if (activePillEl) {{
                if (!activePillEl.getAttribute('data-orig-title')) {{
                    activePillEl.setAttribute('data-orig-title', activePillEl.getAttribute('title') || '当前活跃账号');
                }}
                if (isMasked) {{
                    activePillEl.title = "活跃账号: 已脱敏保护 (点击复制)";
                }} else {{
                    activePillEl.title = activePillEl.getAttribute('data-orig-title') || "当前活跃账号 (点击复制)";
                }}
            }}
        }}

        function toggleAccountMask() {{
            isMasked = !isMasked;
            localStorage.setItem('hub_account_mask', isMasked ? '1' : '0');
            applyAccountMask();
            showToast(isMasked ? "🔒 已开启打码 (再次点击显示明文)" : "👁️ 已显示明文 (再次点击打码脱敏)", "info");
        }}

        function toggleAccountMaskFromSettings(cb) {{
            isMasked = cb.checked;
            localStorage.setItem('hub_account_mask', isMasked ? '1' : '0');
            applyAccountMask();
        }}

        // ⚙️ 控制台设置面板交互逻辑 (Magpie 风格)
        function openSettingsModal() {{
            const backdrop = document.getElementById('settings-modal-backdrop');
            if (backdrop) {{
                backdrop.classList.add('show');
                loadSettingsToUI();
            }}
        }}

        function closeSettingsModal() {{
            const backdrop = document.getElementById('settings-modal-backdrop');
            if (backdrop) backdrop.classList.remove('show');
        }}

        function toggleSettingsModal() {{
            const backdrop = document.getElementById('settings-modal-backdrop');
            if (backdrop && backdrop.classList.contains('show')) {{
                closeSettingsModal();
            }} else {{
                openSettingsModal();
            }}
        }}

        function switchSettingsTab(tabName) {{
            ['gemini', 'warmup', 'display', 'shortcuts'].forEach(t => {{
                const btn = document.getElementById('tab-btn-cfg-' + t);
                const pane = document.getElementById('settings-pane-' + t);
                if (btn) btn.classList.toggle('active', t === tabName);
                if (pane) pane.style.display = (t === tabName) ? 'block' : 'none';
            }});
        }}

        function loadSettingsToUI() {{
            const rotMode = document.getElementById('cfg-rot-mode');
            const rotBtn = document.getElementById('btn-rotation-toggle');
            if (rotMode && rotBtn) {{
                rotMode.value = rotBtn.getAttribute('data-mode') || 'gemini';
            }}
            const maskCb = document.getElementById('cfg-mask-default');
            if (maskCb) maskCb.checked = isMasked;

            const density = localStorage.getItem('hub_table_density') || 'standard';
            const densitySelect = document.getElementById('cfg-table-density');
            if (densitySelect) densitySelect.value = density;

            const defaultSort = localStorage.getItem('hub_default_sort') || 'gemini_5h_desc';
            const sortSelect = document.getElementById('cfg-default-sort');
            if (sortSelect) sortSelect.value = defaultSort;

            const refreshSec = localStorage.getItem('hub_refresh_sec') || '5';
            const refreshSelect = document.getElementById('cfg-refresh-sec');
            if (refreshSelect) refreshSelect.value = refreshSec;

            const hideExhausted = localStorage.getItem('hub_hide_exhausted') === '1';
            const hideCb = document.getElementById('cfg-hide-exhausted');
            if (hideCb) hideCb.checked = hideExhausted;

            fetch('/api/settings').then(r => r.ok ? r.json() : null).then(cfg => {{
                if (!cfg) return;
                if (rotMode && cfg.rotation_mode) rotMode.value = cfg.rotation_mode;
                const thrSel = document.getElementById('cfg-gemini-threshold');
                if (thrSel && cfg.gemini_threshold !== undefined) {{
                    const rawVal = Number(cfg.gemini_threshold);
                    const valStr = rawVal === 0 ? '0' : rawVal.toFixed(2);
                    if (!Array.from(thrSel.options).some(o => Number(o.value) === rawVal)) {{
                        const opt = document.createElement('option');
                        opt.value = valStr;
                        opt.textContent = `${{Math.round(rawVal * 100)}}% (自定义水位)`;
                        thrSel.appendChild(opt);
                    }}
                    const matchOpt = Array.from(thrSel.options).find(o => Number(o.value) === rawVal);
                    if (matchOpt) thrSel.value = matchOpt.value;
                }}
                if (sortSelect && cfg.default_sort) sortSelect.value = cfg.default_sort;
                const warmupCb = document.getElementById('cfg-hourly-warmup');
                if (warmupCb && cfg.hourly_warmup !== undefined) warmupCb.checked = !!cfg.hourly_warmup;
                const warmupModel = document.getElementById('cfg-warmup-model');
                if (warmupModel && cfg.warmup_model) warmupModel.value = (cfg.warmup_model === 'gemini_first' ? 'dual' : cfg.warmup_model);
                const warmupStagger = document.getElementById('cfg-warmup-stagger');
                if (warmupStagger && cfg.warmup_stagger_sec !== undefined) warmupStagger.value = String(cfg.warmup_stagger_sec);
            }}).catch(() => {{}});
        }}

        function onDensityChange(val) {{
            localStorage.setItem('hub_table_density', val);
            applyTableDensity();
        }}

        function applyTableDensity() {{
            const val = localStorage.getItem('hub_table_density') || 'standard';
            const app = document.querySelector('.app-container');
            if (app) {{
                app.classList.remove('density-compact', 'density-standard', 'density-relaxed');
                app.classList.add('density-' + val);
            }}
        }}

        let __tableRefreshIntervalId = null;
        function onRefreshSecChange(val) {{
            localStorage.setItem('hub_refresh_sec', val);
            setupAutoRefreshTimer();
        }}

        function setupAutoRefreshTimer() {{
            if (__tableRefreshIntervalId) {{
                clearInterval(__tableRefreshIntervalId);
                __tableRefreshIntervalId = null;
            }}
            const sec = parseInt(localStorage.getItem('hub_refresh_sec') || '5', 10);
            if (sec > 0) {{
                __tableRefreshIntervalId = setInterval(fetchTableSafely, sec * 1000);
            }}
        }}

        function onHideExhaustedChange(cb) {{
            localStorage.setItem('hub_hide_exhausted', cb.checked ? '1' : '0');
            filterTable();
        }}

        async function saveSettings() {{
            const rotMode = document.getElementById('cfg-rot-mode')?.value || 'gemini';
            const gThreshold = parseFloat(document.getElementById('cfg-gemini-threshold')?.value || '0');
            const defaultSort = document.getElementById('cfg-default-sort')?.value || 'gemini_5h_desc';
            const hourlyWarmup = document.getElementById('cfg-hourly-warmup')?.checked ?? true;
            const warmupModel = document.getElementById('cfg-warmup-model')?.value || 'dual';
            const warmupStagger = parseInt(document.getElementById('cfg-warmup-stagger')?.value || '60', 10);

            localStorage.setItem('hub_default_sort', defaultSort);

            try {{
                await fetch('/api/settings', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        mode: rotMode,
                        gemini_threshold: gThreshold,
                        default_sort: defaultSort,
                        hourly_warmup: hourlyWarmup,
                        warmup_model: warmupModel,
                        warmup_stagger_sec: warmupStagger,
                        account_mask: isMasked,
                        table_density: localStorage.getItem('hub_table_density') || 'standard',
                        auto_refresh_sec: parseInt(localStorage.getItem('hub_refresh_sec') || '5', 10),
                        hide_exhausted: localStorage.getItem('hub_hide_exhausted') === '1'
                    }})
                }});

                const rotBtn = document.getElementById('btn-rotation-toggle');
                if (rotBtn && rotBtn.getAttribute('data-mode') !== rotMode) {{
                    await fetch('/api/toggle-rotation', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ mode: rotMode }})
                    }});
                    fetchTableSafely();
                }}

                closeSettingsModal();
                showToast("⚙️ 设置已成功保存并即时生效", "success");
            }} catch (err) {{
                showToast("❌ 设置保存失败: " + err.message, "error");
            }}
        }}

        let currentFilter = 'all';
        let currentTierFilter = '';
        let __oauthPollTimer = null;
        let __currentOAuthUrl = '';
        let __currentOAuthState = '';

        // 📥 账号导入与纳管中心交互逻辑
        function openImportModal() {{
            const backdrop = document.getElementById('import-modal-backdrop');
            if (backdrop) backdrop.classList.add('show');
        }}

        function closeImportModal() {{
            const backdrop = document.getElementById('import-modal-backdrop');
            if (backdrop) backdrop.classList.remove('show');
            if (__oauthPollTimer) {{
                clearInterval(__oauthPollTimer);
                __oauthPollTimer = null;
            }}
        }}

        function switchImportTab(tabName) {{
            ['oauth', 'sync', 'file'].forEach(t => {{
                const btn = document.getElementById('tab-btn-' + t);
                const pane = document.getElementById('import-pane-' + t);
                if (btn) btn.classList.toggle('active', t === tabName);
                if (pane) pane.style.display = (t === tabName) ? 'block' : 'none';
            }});
        }}

        function copyCurrentOAuthUrl() {{
            if (!__currentOAuthUrl) {{
                showToast("请先点击上方授权按钮生成链接", "info");
                return;
            }}
            navigator.clipboard.writeText(__currentOAuthUrl).then(() => {{
                showToast("✅ 已复制 Google OAuth 授权链接，可粘贴至任意浏览器打开", "success");
            }}).catch(() => {{
                showToast("复制失败，请重试", "error");
            }});
        }}

        // 🌐 启动 Google OAuth 2.0 浏览器一键登录授权流
        async function doStartGoogleOAuth(isolated, btn) {{
            const origText = btn ? btn.innerText : '';
            if (btn) {{
                btn.disabled = true;
                btn.innerText = "⏳ 正在拉起 Google OAuth 授权窗口...";
            }}
            try {{
                const resp = await fetch('/api/oauth/start', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ isolated: !!isolated, open_browser: true }})
                }});
                const data = await resp.json();
                if (!resp.ok || data.status !== 'ok') {{
                    showToast("❌ 启动授权失败: " + (data.message || resp.status), "error");
                    return;
                }}
                __currentOAuthUrl = data.auth_url;
                __currentOAuthState = data.state;

                const statusBox = document.getElementById('oauth-status-box');
                const statusText = document.getElementById('oauth-status-text');
                if (statusBox) statusBox.style.display = 'block';
                if (statusText) statusText.innerText = isolated
                    ? "⏳ 已拉起独立沙盒容器窗口（全新隔离/防串号），请在新窗口完成登录并授权..."
                    : "⏳ 已在浏览器打开 Google 授权页，请完成登录授权（完成后自动入库）...";

                showToast("🚀 已拉起 Google 授权页面，请在浏览器中登录确认", "info");

                if (__oauthPollTimer) clearInterval(__oauthPollTimer);
                __oauthPollTimer = setInterval(async () => {{
                    try {{
                        const pResp = await fetch('/api/oauth/poll?state=' + encodeURIComponent(__currentOAuthState));
                        if (!pResp.ok) return;
                        const pData = await pResp.json();
                        if (pData.status === 'success') {{
                            clearInterval(__oauthPollTimer);
                            __oauthPollTimer = null;
                            if (statusText) statusText.innerText = "✅ 授权成功: " + pData.email;
                            showToast("🎉 " + (pData.message || ("已成功添加账号 " + pData.email)), "success");
                            closeImportModal();
                            fetchTableSafely();
                        }} else if (pData.status === 'error') {{
                            clearInterval(__oauthPollTimer);
                            __oauthPollTimer = null;
                            if (statusText) statusText.innerText = "❌ 授权失败: " + pData.message;
                            showToast("❌ " + pData.message, "error");
                        }}
                    }} catch (e) {{}}
                }}, 1500);
            }} catch (err) {{
                showToast("❌ 请求异常: " + err.message, "error");
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerText = origText;
                }}
            }}
        }}

        // ⚡ 手动粘贴回调 URL 或 Code 兜底解析入库
        async function doSubmitManualOAuthCode(btn) {{
            const input = document.getElementById('oauth-manual-code');
            const val = input ? input.value.trim() : '';
            if (!val) {{
                showToast("❌ 请粘贴 Google 授权回调 URL 或 Code", "error");
                return;
            }}
            const origText = btn ? btn.innerText : '';
            if (btn) {{
                btn.disabled = true;
                btn.innerText = "⏳ 兑换中...";
            }}
            try {{
                const resp = await fetch('/api/oauth/manual_code', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ code_or_url: val }})
                }});
                const data = await resp.json();
                if (resp.ok && data.status === 'ok') {{
                    showToast("🎉 " + data.message, "success");
                    if (input) input.value = '';
                    closeImportModal();
                    fetchTableSafely();
                }} else {{
                    showToast("❌ " + (data.message || "兑换失败"), "error");
                }}
            }} catch (err) {{
                showToast("❌ 请求失败: " + err.message, "error");
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerText = origText;
                }}
            }}
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

            // 🛡️ [版本感知自愈门禁] 检测客户端版本与服务端版本是否一致
            const serverVerMarker = docAll.getElementById('hub-version-marker');
            if (serverVerMarker) {{
                const clientVer = document.body ? document.body.getAttribute('data-hub-version') : null;
                const serverVer = serverVerMarker.getAttribute('data-version');
                if (clientVer && serverVer && clientVer !== serverVer) {{
                    console.warn(`[Hub自愈门禁] 服务端已升版至 ${{serverVer}}，当前客户端为 ${{clientVer}}，立即整页自愈刷新！`);
                    window.location.reload();
                    return;
                }}
            }}

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

            // 🛡️ [表头列数物理一致性自愈门禁] 检测当前页面的表头 th 数量与服务端返回的 tr 单元格数量是否一致
            const theadThs = document.querySelectorAll('.table-wrap table thead th');
            if (trs.length > 0 && theadThs.length > 0) {{
                const firstRowCells = trs[0].querySelectorAll('td, th');
                if (firstRowCells.length > 0 && theadThs.length !== firstRowCells.length) {{
                    console.warn(`[Hub自愈门禁] 表头列数(${{theadThs.length}})与行单元格数(${{firstRowCells.length}})失配，页面结构过时，立即整页自愈刷新！`);
                    window.location.reload();
                    return;
                }}
            }}

            if (tbody && trs.length > 0) {{
                tbody.innerHTML = '';
                trs.forEach(tr => {{
                    tbody.appendChild(document.importNode(tr, true));
                }});
                __cachedTbodyHTML = tbody.innerHTML;
                filterTable();
                applyAccountMask();
                if (typeof initDragSort === 'function') {{
                    initDragSort();
                }}
                if (typeof restoreSelectionState === 'function') {{
                    restoreSelectionState();
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

        // 🏷️ 一键切换账号来源类别（付费 PRO / 学生 PRO / 免费 PRO）
        async function doCycleTier(email, nextTier) {{
            try {{
                const resp = await fetch('/api/set_tier', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ email: email, tier_override: nextTier }})
                }});
                const j = await resp.json();
                if (j && j.ok) {{
                    showToast(j.message || "类别已更新", "success");
                    const tb = document.getElementById('account-tbody');
                    if (tb && window.htmx) htmx.ajax('GET', '/api/table', {{ target: '#account-tbody', swap: 'innerHTML' }});
                    else location.reload();
                }}
            }} catch (e) {{
                showToast("切换类别失败: " + e, "error");
            }}
        }}

        // 🛡️ 一键解封向导：拉起独立容器浏览器并自动定向对应账号，彻底杜绝 Cookie 串号！
        async function doUnblockAccount(email) {{
            showToast("🚀 正在获取最新令牌并拉起 ego 浏览器解封页面...", "info");
            try {{
                const resp = await fetch('/api/unblock', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
                    body: 'email=' + encodeURIComponent(email)
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const html = await resp.text();
                applyTbodyAndOOB(html);
                showToast("✅ 已在 ego 浏览器拉起解封页面！请在窗口登录并确认，后台将自动监听解锁！", "success");
            }} catch (err) {{
                showToast("❌ 启动解封失败: " + err.message, "error");
            }}
        }}

        // 🔄 三态循环切换自动轮换开关直通函数 (全局 Gemini ➔ 仅付费 PRO ➔ 关闭 ➔ 全局 Gemini)
        async function cycleAutoRotation(btn) {{
            btn.disabled = true;
            try {{
                const resp = await fetch('/api/toggle-rotation', {{
                    method: 'POST'
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const res = await resp.json();
                const mode = res.mode || (res.enabled ? (res.policy === 'paid_pro_only' ? 'paid_pro' : 'gemini') : 'off');
                btn.setAttribute('data-mode', mode);

                if (mode === 'gemini') {{
                    btn.className = "btn btn-top btn-rotation-gemini font-mono";
                    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><polygon points="5 3 19 12 5 21 5 3"/></svg>全局 Gemini';
                    btn.title = "当前模式：全局 Gemini 轮转（全池账号参与耗尽自动切号；点击切换为仅付费 PRO 轮转）";
                    showToast("⚡ 已切换为【全局 Gemini 轮转】：全池账号参与自动切号", "success");
                }} else if (mode === 'paid_pro') {{
                    btn.className = "btn btn-top btn-rotation-claude font-mono";
                    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><polygon points="5 3 19 12 5 21 5 3"/></svg>付费 PRO';
                    btn.title = "当前模式：仅付费 PRO 轮转（只在付费 PRO 账号间自动切号，保留 Gemini 4 体验；点击关闭轮转）";
                    showToast("👑 已切换为【付费 PRO 轮转】：仅在付费 PRO 账号间自动切号", "info");
                }} else {{
                    btn.className = "btn btn-top btn-rotation-off font-mono";
                    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>已关闭';
                    btn.title = "当前模式：彻底关闭自动轮转（看门狗已冻结，不自动切号；点击开启全局 Gemini 轮转）";
                    showToast("🚫 已彻底关闭自动轮转：看门狗已冻结，不会自动切号", "warning");
                }}
            }} catch (err) {{
                showToast("❌ 切换轮换状态失败: " + err.message, "error");
            }} finally {{
                btn.disabled = false;
            }}
        }}
        window.toggleAutoRotation = cycleAutoRotation;

        let currentPage = 1;
        const PAGE_SIZE = 20;
        let __cachedTbodyHTML = '';
        let currentSortMode = 'default'; // 'default' | 'gemini4_w_desc' | 'gemini_w_asc' | 'gemini_5h_asc' | 'claude_w_asc' | 'claude_5h_asc'

        // 🔀 更新 类别 / Gemini / Claude 表头排序角标指示器
        function updateSortBadges() {{
            const tierBadge = document.getElementById('sort-tier-badge');
            const gBadge = document.getElementById('sort-gemini-badge');
            const cBadge = document.getElementById('sort-claude-badge');

            if (tierBadge) {{
                if (currentSortMode === 'tier_asc') {{
                    tierBadge.textContent = '付费优先';
                    tierBadge.style.display = 'inline-flex';
                }} else {{
                    tierBadge.textContent = '';
                    tierBadge.style.display = 'none';
                }}
            }}

            if (gBadge) {{
                if (currentSortMode === 'gemini_5h_desc') {{
                    gBadge.textContent = '5h多→少';
                    gBadge.style.display = 'inline-flex';
                }} else if (currentSortMode === 'gemini_w_desc') {{
                    gBadge.textContent = '周多→少';
                    gBadge.style.display = 'inline-flex';
                }} else if (currentSortMode === 'gemini_5h_asc') {{
                    gBadge.textContent = '5h少→多';
                    gBadge.style.display = 'inline-flex';
                }} else if (currentSortMode === 'gemini_w_asc') {{
                    gBadge.textContent = '周少→多';
                    gBadge.style.display = 'inline-flex';
                }} else {{
                    gBadge.textContent = '';
                    gBadge.style.display = 'none';
                }}
            }}

            if (cBadge) {{
                if (currentSortMode === 'claude_w_asc') {{
                    cBadge.textContent = '周少→多';
                    cBadge.style.display = 'inline-flex';
                }} else if (currentSortMode === 'claude_5h_asc') {{
                    cBadge.textContent = '5h少→多';
                    cBadge.style.display = 'inline-flex';
                }} else {{
                    cBadge.textContent = '';
                    cBadge.style.display = 'none';
                }}
            }}
        }}

        // 🎯 类别表头循环点击排序：付费 PRO → 免费 PRO → FREE → 恢复默认
        function cycleTierSort() {{
            if (currentSortMode !== 'tier_asc') {{
                currentSortMode = 'tier_asc';
                showToast("📊 已按账号类别（付费 PRO → 免费 PRO → FREE）排序", "info");
            }} else {{
                currentSortMode = 'default';
                showToast("🔄 已恢复账号列表默认排序", "info");
            }}
            currentPage = 1;
            updateSortBadges();
            filterTable();
        }}

        // 🎯 Gemini 表头三态循环点击排序：周额度(少→多) → 5h额度(少→多) → 恢复默认
        function cycleGeminiSort() {{
            if (currentSortMode === 'default' || currentSortMode.startsWith('claude_')) {{
                currentSortMode = 'gemini_w_asc';
                showToast("📊 已按 Gemini 周额度 (从少到多) 升序排列", "info");
            }} else if (currentSortMode === 'gemini_w_asc') {{
                currentSortMode = 'gemini_5h_asc';
                showToast("📊 已按 Gemini 5h 额度 (从少到多) 升序排列", "info");
            }} else {{
                currentSortMode = 'default';
                showToast("🔄 已恢复账号列表默认排序", "info");
            }}
            currentPage = 1;
            updateSortBadges();
            filterTable();
        }}

        // 🎯 Claude 表头三态循环点击排序：周额度(少→多) → 5h额度(少→多) → 恢复默认
        function cycleClaudeSort() {{
            if (currentSortMode === 'default' || currentSortMode.startsWith('gemini_')) {{
                currentSortMode = 'claude_w_asc';
                showToast("📊 已按 Claude 周额度 (从少到多) 升序排列", "info");
            }} else if (currentSortMode === 'claude_w_asc') {{
                currentSortMode = 'claude_5h_asc';
                showToast("📊 已按 Claude 5h 额度 (从少到多) 升序排列", "info");
            }} else {{
                currentSortMode = 'default';
                showToast("🔄 已恢复账号列表默认排序", "info");
            }}
            currentPage = 1;
            updateSortBadges();
            filterTable();
        }}

        // 页面初始加载时初始化原始行数据（强制移除任何历史暗黑主题残留，100% 保持 Mac 原版浅色 Neo-Brutalism）
        window.addEventListener('DOMContentLoaded', function() {{
            localStorage.removeItem('hub_theme');
            document.body.classList.remove('theme-omarchy');

            const tbody = document.getElementById('account-tbody');
            if (tbody && tbody.children.length > 0) {{
                __cachedTbodyHTML = tbody.innerHTML;
            }}
            updateSortBadges();
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
            document.querySelectorAll('.filter-tab[data-filter]').forEach(b => b.classList.remove('active'));
            if (btn) btn.classList.add('active');
            filterTable();
        }}

        function toggleTierFilter(tierCode, btn) {{
            currentTierFilter = (currentTierFilter === tierCode) ? '' : tierCode;
            currentPage = 1;
            document.querySelectorAll('.tier-tab[data-tier-filter]').forEach(b => {{
                b.classList.toggle('active', b.getAttribute('data-tier-filter') === currentTierFilter);
            }});
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
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;

            const allRows = Array.from(tbody.querySelectorAll('tr.account-row'));
            if (allRows.length === 0) return;

            // 1. 🔀 根据 currentSortMode 对全量账号行进行排序并重排 DOM
            allRows.sort((a, b) => {{
                if (currentSortMode !== 'default') {{
                    let valA = 0;
                    let valB = 0;
                    if (currentSortMode === 'tier_asc') {{
                        valA = parseInt(a.getAttribute('data-tier-rank') || '2', 10);
                        valB = parseInt(b.getAttribute('data-tier-rank') || '2', 10);
                        if (valA !== valB) return valA - valB;
                    }} else if (currentSortMode === 'gemini_5h_desc') {{
                        valA = parseFloat(a.getAttribute('data-gemini-5h') || '0');
                        valB = parseFloat(b.getAttribute('data-gemini-5h') || '0');
                        if (valA !== valB) return valB - valA;
                    }} else if (currentSortMode === 'gemini_w_desc') {{
                        valA = parseFloat(a.getAttribute('data-gemini-w') || '0');
                        valB = parseFloat(b.getAttribute('data-gemini-w') || '0');
                        if (valA !== valB) return valB - valA;
                    }} else if (currentSortMode === 'gemini_w_asc') {{
                        valA = parseFloat(a.getAttribute('data-gemini-w') || '0');
                        valB = parseFloat(b.getAttribute('data-gemini-w') || '0');
                        if (valA !== valB) return valA - valB;
                    }} else if (currentSortMode === 'gemini_5h_asc') {{
                        valA = parseFloat(a.getAttribute('data-gemini-5h') || '0');
                        valB = parseFloat(b.getAttribute('data-gemini-5h') || '0');
                        if (valA !== valB) return valA - valB;
                    }} else if (currentSortMode === 'claude_5h_desc') {{
                        valA = parseFloat(a.getAttribute('data-claude-5h') || '0');
                        valB = parseFloat(b.getAttribute('data-claude-5h') || '0');
                        if (valA !== valB) return valB - valA;
                    }} else if (currentSortMode === 'claude_w_asc') {{
                        valA = parseFloat(a.getAttribute('data-claude-w') || '0');
                        valB = parseFloat(b.getAttribute('data-claude-w') || '0');
                        if (valA !== valB) return valA - valB;
                    }} else if (currentSortMode === 'claude_5h_asc') {{
                        valA = parseFloat(a.getAttribute('data-claude-5h') || '0');
                        valB = parseFloat(b.getAttribute('data-claude-5h') || '0');
                        if (valA !== valB) return valA - valB;
                    }}
                }}
                // 默认模式或数值相同时按原始入库索引稳定对齐
                const origA = parseInt(a.getAttribute('data-orig-idx') || '0', 10);
                const origB = parseInt(b.getAttribute('data-orig-idx') || '0', 10);
                return origA - origB;
            }});
            allRows.forEach(tr => tbody.appendChild(tr));

            // 2. 搜索框实时过滤
            const input = document.getElementById('account-search');
            const q = input ? input.value.toLowerCase().trim() : '';
            const clearBtn = document.getElementById('clear-search');
            if (clearBtn) clearBtn.style.display = q ? 'inline-block' : 'none';

            // 3. 状态与三档类别组合过滤
            const hideExhausted = localStorage.getItem('hub_hide_exhausted') === '1';
            let paidCount = 0;
            let freeProCount = 0;
            let freeCount = 0;
            const matchedRows = [];
            allRows.forEach(tr => {{
                const email = tr.getAttribute('data-email') || '';
                const tier = tr.getAttribute('data-tier') || 'FREE';
                if (tier === 'PAID_PRO') paidCount++;
                else if (tier === 'FREE_PRO') freeProCount++;
                else freeCount++;

                const cver = tr.getAttribute('data-claude-ver') || '';
                const isRegRestricted = tr.getAttribute('data-region-restricted') === '1';
                const matchQuery = !q || email.toLowerCase().includes(q)
                    || (q === '5.5' && cver === '5.5')
                    || (q === '4.6' && cver === '4.6')
                    || (q === '下架' && cver === '4.6')
                    || ((q === '付费' || q === 'paid') && tier === 'PAID_PRO')
                    || ((q === '免费pro' || q === 'freepro') && tier === 'FREE_PRO')
                    || (q === 'pro' && (tier === 'PAID_PRO' || tier === 'FREE_PRO'))
                    || (q === 'free' && tier === 'FREE')
                    || ((q === 'cn' || q === '中国' || q === '解锁') && isRegRestricted);

                const g5 = parseFloat(tr.getAttribute('data-gemini-5h') || '-1');
                const gw = parseFloat(tr.getAttribute('data-gemini-w') || '1.0');
                const cw = parseFloat(tr.getAttribute('data-claude-w') || '1.0');
                let matchTab = true;
                if (currentFilter === 'ver55') {{
                    matchTab = (cver === '5.5');
                }} else if (currentFilter === 'ver46') {{
                    matchTab = (cver === '4.6');
                }} else if (currentFilter === 'usable') {{
                    matchTab = (!isRegRestricted && gw >= 0.005);
                }} else if (currentFilter === 'healthy') {{
                    matchTab = (!isRegRestricted && gw >= 0.5 && cw >= 0.5);
                }} else if (currentFilter === 'warning') {{
                    matchTab = (gw >= 0.005 && (gw < 0.15 || cw < 0.15 || (g5 >= 0 && g5 < 0.15)));
                }} else if (currentFilter === 'exhausted') {{
                    matchTab = (gw < 0.005);
                }}

                const matchTier = !currentTierFilter || (tier === currentTierFilter);
                const matchHideExhausted = !hideExhausted || (gw >= 0.005);

                if (matchQuery && matchTab && matchTier && matchHideExhausted) {{
                    matchedRows.push(tr);
                }} else {{
                    tr.style.display = 'none';
                }}
            }});

            const allTab = document.querySelector('.filter-tab[data-filter="all"]');
            if (allTab) allTab.textContent = `全部 (${{allRows.length}})`;

            // 4. 🎯 单页上限 15 个的分页算法
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

            // 5. 顶栏计数器与底部分页栏
            const counter = document.getElementById('filter-counter');
            if (counter) {{
                counter.innerHTML = `显示: <b>${{Math.min(PAGE_SIZE, totalMatched)}}</b> / ${{allRows.length}}`;
            }}

            const pageIndicator = document.getElementById('page-indicator');
            if (pageIndicator) {{
                pageIndicator.innerHTML = `第 <b>${{currentPage}}</b> / ${{totalPages}} 页`;
            }}
            const pageTotal = document.getElementById('page-total');
            if (pageTotal) {{
                pageTotal.innerHTML = `共 ${{totalMatched}} 项 · 付费PRO ${{paidCount}} · 免费PRO ${{freeProCount}} · FREE ${{freeCount}}`;
            }}
            const btnPrev = document.getElementById('btn-prev-page');
            const btnNext = document.getElementById('btn-next-page');
            if (btnPrev) btnPrev.disabled = (currentPage <= 1);
            if (btnNext) btnNext.disabled = (currentPage >= totalPages);

            updateSortBadges();
            restoreSelectionState();
            applyAccountMask();
        }}

        // 支持 URL 参数 ?filter=usable 自动触发筛选与 ?sort=gemini_w 自动触发排序
        window.addEventListener('DOMContentLoaded', () => {{
            const urlParams = new URLSearchParams(window.location.search);
            const f = urlParams.get('filter');
            if (f) {{
                const btn = document.querySelector(`.filter-tab[data-filter="${{f}}"]`);
                if (btn) setFilter(f, btn);
            }}
            const s = urlParams.get('sort');
            if (s === 'gemini_w') {{
                cycleGeminiSort();
            }} else if (s === 'gemini_5h') {{
                cycleGeminiSort();
                cycleGeminiSort();
            }} else if (s === 'claude_w') {{
                cycleClaudeSort();
            }} else if (s === 'claude_5h') {{
                cycleClaudeSort();
                cycleClaudeSort();
            }}
        }});

        // ⌨️ 全局键盘快捷键 (Magpie 标准快捷键体系)
        window.addEventListener('keydown', (e) => {{
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (e.key === 'Escape') {{
                closeSettingsModal();
                closeImportModal();
                closeNeoModal(false);
            }} else if (e.key === 's' || e.key === 'S') {{
                e.preventDefault();
                toggleSettingsModal();
            }} else if (e.key === 'm' || e.key === 'M') {{
                e.preventDefault();
                toggleAccountMask();
            }} else if (e.key === 'r' || e.key === 'R') {{
                e.preventDefault();
                const refreshBtn = document.querySelector('.btn-refresh-all');
                if (refreshBtn) doRefreshQuota(refreshBtn);
            }}
        }});

        // 窗口重新获得焦点时立即静默触发一次最新状态同步
        window.addEventListener('focus', () => {{
            fetchTableSafely();
        }});

        // 定时同步调度与初态挂载
        setupAutoRefreshTimer();
        window.addEventListener('DOMContentLoaded', () => {{
            applyAccountMask();
            applyTableDensity();
            const defSort = localStorage.getItem('hub_default_sort');
            if (defSort && defSort !== 'default' && currentSortMode === 'default') {{
                currentSortMode = defSort;
                updateSortBadges();
                filterTable();
            }}
        }});

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
            if (currentSortMode !== 'default') {{
                showToast("⚠️ 当前处于排序模式，请先点击表头恢复默认排序后再调序", "warning");
                return;
            }}
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

            // 1. 即时平滑更新前端行号与原始索引
            tbody.querySelectorAll('tr.account-row').forEach((r, i) => {{
                r.setAttribute('data-orig-idx', i + 1);
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
                    if (currentSortMode !== 'default') {{
                        e.preventDefault();
                        showToast("⚠️ 当前处于排序模式，请先点击表头恢复默认排序后再拖拽", "warning");
                        return;
                    }}
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

        // ═══════════════════════════════════════════════════════════
        // ☑️ 批量勾选、选区导出与安全防误删系统 (抗 5s HTMX 轮询刷新状态自愈)
        // ═══════════════════════════════════════════════════════════
        const selectedEmails = new Set();

        // 单行勾选改变
        function onRowSelectChange(cb) {{
            const email = cb.getAttribute('data-email') || cb.value;
            if (!email) return;
            const tr = cb.closest('tr.account-row');
            if (cb.checked) {{
                selectedEmails.add(email);
                if (tr) tr.classList.add('is-row-selected');
            }} else {{
                selectedEmails.delete(email);
                if (tr) tr.classList.remove('is-row-selected');
            }}
            updateBatchActionBar();
            updateMasterCheckboxState();
        }}

        // 表头全选 / 反选（仅针对当前经过筛选后可见的行）
        function toggleMasterSelect(masterCb) {{
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;
            const visibleRows = Array.from(tbody.querySelectorAll('tr.account-row')).filter(r => r.style.display !== 'none');
            const shouldCheck = masterCb.checked;
            visibleRows.forEach(tr => {{
                const email = tr.getAttribute('data-email');
                const cb = tr.querySelector('.row-select-cb');
                if (shouldCheck) {{
                    selectedEmails.add(email);
                    if (cb) cb.checked = true;
                    tr.classList.add('is-row-selected');
                }} else {{
                    selectedEmails.delete(email);
                    if (cb) cb.checked = false;
                    tr.classList.remove('is-row-selected');
                }}
            }});
            updateBatchActionBar();
        }}

        // 清空所有已选
        function clearAllSelections() {{
            selectedEmails.clear();
            const tbody = document.getElementById('account-tbody');
            if (tbody) {{
                tbody.querySelectorAll('.row-select-cb').forEach(cb => cb.checked = false);
                tbody.querySelectorAll('tr.account-row').forEach(tr => tr.classList.remove('is-row-selected'));
            }}
            const masterCb = document.getElementById('master-select-cb');
            if (masterCb) {{
                masterCb.checked = false;
                masterCb.indeterminate = false;
            }}
            updateBatchActionBar();
        }}

        // 更新批量操作栏显示与计数
        function updateBatchActionBar() {{
            const bar = document.getElementById('batch-action-bar');
            const countEl = document.getElementById('batch-selected-count');
            const count = selectedEmails.size;
            if (countEl) countEl.textContent = count;
            if (bar) {{
                bar.style.display = count > 0 ? 'inline-flex' : 'none';
            }}
        }}

        // 更新表头全选框的状态（对齐当前可见行：全选/部分选中/未选）
        function updateMasterCheckboxState() {{
            const masterCb = document.getElementById('master-select-cb');
            if (!masterCb) return;
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;
            const visibleRows = Array.from(tbody.querySelectorAll('tr.account-row')).filter(r => r.style.display !== 'none');
            if (visibleRows.length === 0) {{
                masterCb.checked = false;
                masterCb.indeterminate = false;
                return;
            }}
            let checkedCount = 0;
            visibleRows.forEach(tr => {{
                const email = tr.getAttribute('data-email');
                if (selectedEmails.has(email)) checkedCount++;
            }});
            if (checkedCount === 0) {{
                masterCb.checked = false;
                masterCb.indeterminate = false;
            }} else if (checkedCount === visibleRows.length) {{
                masterCb.checked = true;
                masterCb.indeterminate = false;
            }} else {{
                masterCb.checked = false;
                masterCb.indeterminate = true;
            }}
        }}

        // 状态自愈：当 DOM 被 applyTbodyAndOOB 或 filterTable 重新渲染时，遍历 DOM 回填勾选态
        function restoreSelectionState() {{
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;
            tbody.querySelectorAll('tr.account-row').forEach(tr => {{
                const email = tr.getAttribute('data-email');
                const cb = tr.querySelector('.row-select-cb');
                if (selectedEmails.has(email)) {{
                    if (cb) cb.checked = true;
                    tr.classList.add('is-row-selected');
                }} else {{
                    if (cb) cb.checked = false;
                    tr.classList.remove('is-row-selected');
                }}
            }});
            updateBatchActionBar();
            updateMasterCheckboxState();
        }}

        // 批量导出选中的账号
        async function doBatchExport() {{
            if (selectedEmails.size === 0) {{
                showToast("⚠️ 请先勾选要导出的账号", "warning");
                return;
            }}
            showToast(`⏳ 正在打包导出 ${{selectedEmails.size}} 个账号凭据...`, "info");
            try {{
                const resp = await fetch('/api/export_selected', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ emails: Array.from(selectedEmails) }})
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const blob = await resp.blob();
                const now = new Date();
                const pad = n => String(n).padStart(2, '0');
                const ts = `${{now.getFullYear()}}${{pad(now.getMonth()+1)}}${{pad(now.getDate())}}_${{pad(now.getHours())}}${{pad(now.getMinutes())}}${{pad(now.getSeconds())}}`;
                const filename = `antigravity_selected_accounts_${{ts}}.json`;

                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                showToast(`✅ 已成功导出 ${{selectedEmails.size}} 个账号！`, "success");
            }} catch (err) {{
                showToast("❌ 导出失败: " + err.message, "error");
            }}
        }}

        // 批量删除选中的账号（带在用拦截与自动归档）
        async function doBatchDelete() {{
            if (selectedEmails.size === 0) {{
                showToast("⚠️ 请先勾选要删除的账号", "warning");
                return;
            }}
            // 嗅探当前在用活跃账号
            let activeEmail = "";
            const activeTr = document.querySelector('tr.account-row[data-is-active="1"]');
            if (activeTr) {{
                activeEmail = activeTr.getAttribute('data-email') || "";
            }}
            if (!activeEmail) {{
                const pill = document.getElementById('active-email-pill');
                if (pill) {{
                    const text = pill.textContent || "";
                    const m = text.match(/([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+)/);
                    if (m) activeEmail = m[1];
                }}
            }}

            const allSelected = Array.from(selectedEmails);
            const includesActive = activeEmail && selectedEmails.has(activeEmail);
            const toDelete = allSelected.filter(e => e !== activeEmail);

            if (includesActive && toDelete.length === 0) {{
                alert(`❌ 所选账号为当前【在用】护航账号（${{activeEmail}}），受安全门禁保护严禁删除！\\n\\n如需删除，请先在列表中切换至其他可用账号。`);
                return;
            }}

            let confirmMsg = `⚠️ 确定要删除选中的 ${{toDelete.length}} 个账号吗？\\n\\n`;
            if (includesActive) {{
                confirmMsg += `🛡️ 注意：所选的【在用】护航账号（${{activeEmail}}）将受保护自动保留，仅删除其余 ${{toDelete.length}} 个账号。\\n\\n`;
            }}
            confirmMsg += `数据将自动归档至 deleted_accounts_archive.json，删除后列表不再展示。是否继续？`;

            if (!confirm(confirmMsg)) return;

            showToast(`⏳ 正在执行安全删除与归档 (${{toDelete.length}} 个账号)...`, "info");
            try {{
                const resp = await fetch('/api/delete_accounts', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ emails: toDelete }})
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const html = await resp.text();
                toDelete.forEach(e => selectedEmails.delete(e));
                applyTbodyAndOOB(html);
                showToast(`🗑️ 已成功安全删除并归档 ${{toDelete.length}} 个账号！`, "success");
            }} catch (err) {{
                showToast("❌ 删除失败: " + err.message, "error");
            }}
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


OAUTH_STATES: Dict[str, Dict[str, Any]] = {}


class HubHTTPRequestHandler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
            logger.debug(f"客户端连接提前断开: {self.client_address[0]}")

    def log_message(self, format, *args):
        try:
            msg = format % args
            if "/api/table" not in msg and "/api/oauth/poll" not in msg:
                logger.info(f"{self.client_address[0]} - {msg}")
        except Exception:
            pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/static/htmx.min.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(HTMX_JS_BYTES)
            return
        elif parsed.path == "/logo.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(LOGO_PNG_BYTES)
            return
        elif parsed.path in ("/favicon.ico", "/favicon.png"):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(FAVICON_PNG_BYTES)
            return
        elif parsed.path == "/app_icon_512.png":
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(APP_ICON_512_BYTES)
            return
        elif parsed.path == "/" or parsed.path == "/index.html":
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
        elif parsed.path == "/api/settings":
            cfg = get_hub_settings()
            rot_cfg = get_auto_rotation_config()
            cfg["rotation_mode"] = rot_cfg.get("mode", "gemini")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(cfg).encode("utf-8"))
            return
        elif parsed.path == "/api/rotation-status":
            cfg = get_auto_rotation_config()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(cfg).encode("utf-8"))
            return
        elif parsed.path == "/api/export":
            from hub.importer import export_accounts_backup
            backup_data = export_accounts_backup(ACCOUNTS_HUB_FILE)
            resp_bytes = json.dumps(backup_data, indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="antigravity_accounts_backup.json"')
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)
            return
        elif parsed.path == "/api/oauth/poll":
            qs = urllib.parse.parse_qs(parsed.query)
            state = qs.get("state", [""])[0]
            info = OAUTH_STATES.get(state, {"status": "pending", "email": "", "message": ""})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(info, ensure_ascii=False).encode("utf-8"))
            return
        elif parsed.path == "/oauth-callback":
            from hub.importer import exchange_oauth_code_and_ingest
            qs = urllib.parse.parse_qs(parsed.query)
            code = qs.get("code", [""])[0]
            state = qs.get("state", [""])[0]
            err = qs.get("error", [""])[0]
            redirect_uri = f"http://127.0.0.1:{SERVER_PORT}/oauth-callback"
            if state in OAUTH_STATES and OAUTH_STATES[state].get("redirect_uri"):
                redirect_uri = OAUTH_STATES[state]["redirect_uri"]

            if err:
                msg = f"Google 授权被拒绝或取消: {err}"
                if state:
                    OAUTH_STATES[state] = {"status": "error", "email": "", "message": msg}
                ok, email = False, ""
            else:
                ok, email, msg = exchange_oauth_code_and_ingest(code, redirect_uri, accounts_file=ACCOUNTS_HUB_FILE)
                if state:
                    OAUTH_STATES[state] = {
                        "status": "success" if ok else "error",
                        "email": email,
                        "message": msg
                    }
                if ok:
                    threading.Thread(target=ENGINE.refresh_all_quotas, daemon=True).start()

            bg_color = "#10B981" if ok else "#EF4444"
            title_text = "✅ Google OAuth 授权成功！" if ok else "❌ Google OAuth 授权失败"
            cb_html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title_text}</title>
<style>
body {{ background:#F4F0EA; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }}
.box {{ background:#FFFFFF; border:3px solid #000000; border-radius:8px; box-shadow:6px 6px 0px #000000; width:460px; overflow:hidden; }}
.hdr {{ background:{bg_color}; color:#000000; padding:14px 18px; font-size:15px; font-weight:900; border-bottom:3px solid #000000; }}
.bdy {{ padding:20px 18px; font-size:13px; font-weight:700; line-height:1.6; color:#111827; }}
</style></head><body>
<div class="box">
  <div class="hdr">{title_text}</div>
  <div class="bdy">{msg}<br><br><span style="color:#4B5563;font-size:11.5px;">此窗口将在 2 秒后自动关闭，请返回 Antigravity Hub 看板...</span></div>
</div>
<script>setTimeout(function(){{ window.close(); }}, 1800);</script>
</body></html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(cb_html.encode("utf-8"))
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
            # 异步启动全池 PRO 账号随机错峰真实预热线程，绝不阻塞前端界面
            threading.Thread(target=ENGINE.run_hourly_staggered_warmup, kwargs={"force": True}, daemon=True).start()
            logger.info("🔥 [全池随机错峰预热] 用户触发立即预热，后台真实 1-token 激活线程已启动")
            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        elif parsed.path == "/api/settings":
            try:
                prev_warmup = bool(get_hub_settings().get("hourly_warmup", True))
                data = json.loads(post_data)
                updated = save_hub_settings(data)
                if "mode" in data:
                    set_auto_rotation_config(mode=data["mode"])
                if not prev_warmup and bool(updated.get("hourly_warmup", True)):
                    threading.Thread(
                        target=ENGINE.run_hourly_staggered_warmup,
                        kwargs={"force": False},
                        daemon=True,
                    ).start()
                resp_bytes = json.dumps(updated).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(resp_bytes)
                return
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return

        elif parsed.path == "/api/toggle-rotation":
            cur_cfg = get_auto_rotation_config()
            cur_mode = cur_cfg.get("mode", "gemini")

            req_mode = ""
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    req_mode = str(req_j.get("mode", "")).strip()
                else:
                    req_mode = params.get("mode", [""])[0].strip()
            except Exception:
                pass

            if req_mode in ("gemini", "paid_pro", "off"):
                next_mode = req_mode
            else:
                if cur_mode == "gemini":
                    next_mode = "paid_pro"
                elif cur_mode == "paid_pro":
                    next_mode = "off"
                else:
                    next_mode = "gemini"

            new_cfg = set_auto_rotation_config(mode=next_mode)
            logger.info(f"🔄 [轮换开关三态切换] 用户通过 Web UI 切换自动轮换模式: {cur_mode} -> {next_mode}")
            resp_bytes = json.dumps(new_cfg).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(resp_bytes)
            return

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
                    data["accounts_order"] = list(reordered.keys())
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
                        if not raw_url:
                            raw_url = f"https://myaccount.google.com/security?authuser={urllib.parse.quote(email)}"

                        if "&authuser" in raw_url:
                            fixed_raw = raw_url.replace("&authuser", f"&authuser={urllib.parse.quote(email)}")
                        else:
                            fixed_raw = f"{raw_url}&authuser={urllib.parse.quote(email)}"
                        smart_url = f"https://accounts.google.com/AccountChooser?Email={urllib.parse.quote(email)}&continue={urllib.parse.quote(fixed_raw)}"
                        profile_name = get_account_browser_profile(email)

                        # 方案 A 强隔离：强制使用该账号专属独立浏览器容器 (--user-data-dir)，彻底杜绝 Cookie 串号
                        launch_browser_for_auth(smart_url, isolated=True, profile_name=profile_name)
                        logger.info(f"🚀 [一键解封·独立容器] 已为 {email} 拉起独立容器 ({profile_name}): {smart_url}")

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

        elif parsed.path == "/api/region_unlock":
            target_email = ""
            custom_url = ""
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    target_email = str(req_j.get("email") or "").strip().lower()
                    custom_url = str(req_j.get("url") or "").strip()
                else:
                    params = urllib.parse.parse_qs(post_data)
                    target_email = (params.get("email", [""])[0] or "").strip().lower()
                    custom_url = (params.get("url", [""])[0] or "").strip()
            except Exception:
                pass
            target_url = custom_url if custom_url.startswith("https://") else build_region_change_url(target_email)
            profile_name = get_account_browser_profile(target_email)
            ok = launch_browser_for_auth(target_url, isolated=True, profile_name=profile_name)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok, "email": target_email, "profile": profile_name, "url": target_url}, ensure_ascii=False).encode("utf-8"))

        elif parsed.path == "/api/set_tier":
            target_email = ""
            tier_override = ""
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    target_email = str(req_j.get("email") or "").strip().lower()
                    tier_override = str(req_j.get("tier_override") or req_j.get("tier") or "").strip().upper()
                else:
                    params = urllib.parse.parse_qs(post_data)
                    target_email = (params.get("email", [""])[0] or "").strip().lower()
                    tier_override = (params.get("tier_override", params.get("tier", [""]))[0] or "").strip().upper()
            except Exception:
                pass
            allowed = ("", "AUTO", "PAID_PRO", "STUDENT_PRO", "FREE_PRO", "FREE")
            ok = False
            msg = "invalid parameters"
            if target_email and tier_override in allowed:
                data = ENGINE.load_accounts()
                acc = data.get("accounts", {}).get(target_email)
                if isinstance(acc, dict):
                    if tier_override in ("", "AUTO"):
                        acc.pop("tier_override", None)
                    else:
                        acc["tier_override"] = tier_override
                    t_code, t_disp, is_pro, has_5h = classify_account_tier(acc)
                    acc["tier"] = t_code
                    acc["tier_display"] = t_disp
                    acc["pro"] = is_pro
                    acc["has_5h"] = has_5h
                    acc["has_neon"] = detect_account_has_neon(acc)
                    ENGINE.save_accounts(data)
                    ok = True
                    msg = f"已切换 {target_email} 类别为 {t_disp}"
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False).encode("utf-8"))

        elif parsed.path == "/api/set_proxy":
            target_email = ""
            proxy_url = ""
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    target_email = str(req_j.get("email") or "").strip().lower()
                    proxy_url = str(req_j.get("proxy_url") or "").strip()
                else:
                    params = urllib.parse.parse_qs(post_data)
                    target_email = (params.get("email", [""])[0] or "").strip().lower()
                    proxy_url = (params.get("proxy_url", [""])[0] or "").strip()
            except Exception:
                pass
            ok = False
            msg = "invalid email"
            if target_email:
                data = ENGINE.load_accounts()
                acc = data.get("accounts", {}).get(target_email)
                if isinstance(acc, dict):
                    acc["proxy_url"] = proxy_url
                    ENGINE.save_accounts(data)
                    ok = True
                    msg = f"已更新 {target_email} 独立代理配置"
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False).encode("utf-8"))

        elif parsed.path == "/api/oauth/start":
            from hub.importer import build_google_oauth_url
            # 方案 A 强隔离：OAuth 登录默认强制启用独立浏览器容器，避免日常浏览器 Cookie 串号
            isolated = True
            open_browser = True
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    isolated = bool(req_j.get("isolated", True))
                    open_browser = bool(req_j.get("open_browser", True))
            except Exception:
                pass

            state = f"ag_{int(time.time())}_{random.randint(1000, 9999)}"
            redirect_uri = f"http://127.0.0.1:{SERVER_PORT}/oauth-callback"
            auth_url = build_google_oauth_url(redirect_uri=redirect_uri, state=state)
            OAUTH_STATES[state] = {
                "status": "pending",
                "created_at": int(time.time()),
                "redirect_uri": redirect_uri,
                "auth_url": auth_url,
                "email": "",
                "message": ""
            }
            if open_browser:
                try:
                    launch_browser_for_auth(auth_url, isolated=isolated, profile_name=f"oauth_{state}")
                except Exception as e:
                    logger.warning(f"拉起浏览器异常: {e}")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "state": state,
                "auth_url": auth_url,
                "redirect_uri": redirect_uri
            }, ensure_ascii=False).encode("utf-8"))
            return

        elif parsed.path == "/api/oauth/manual_code":
            from hub.importer import exchange_oauth_code_and_ingest
            code_or_url = ""
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    code_or_url = str(req_j.get("code_or_url") or "")
                else:
                    code_or_url = params.get("code_or_url", [""])[0]
            except Exception:
                code_or_url = post_data

            redirect_uri = f"http://127.0.0.1:{SERVER_PORT}/oauth-callback"
            ok, email, msg = exchange_oauth_code_and_ingest(code_or_url, redirect_uri, accounts_file=ACCOUNTS_HUB_FILE)
            if ok:
                threading.Thread(target=ENGINE.refresh_all_quotas, daemon=True).start()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "error", "email": email, "message": msg}, ensure_ascii=False).encode("utf-8"))
            return

        elif parsed.path == "/api/ingest_active":
            from hub.importer import ingest_system_keychain_or_creds
            ok, email, msg = ingest_system_keychain_or_creds(ACCOUNTS_HUB_FILE)
            if ok:
                threading.Thread(target=ENGINE.refresh_all_quotas, daemon=True).start()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "error", "email": email, "message": msg}).encode("utf-8"))
            return

        elif parsed.path == "/api/import":
            from hub.importer import import_accounts_payload
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

        elif parsed.path == "/api/export_selected":
            target_emails = []
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    target_emails = req_j.get("emails", [])
                else:
                    target_emails = params.get("emails[]", params.get("emails", []))
            except Exception as e:
                logger.error(f"解析 export_selected 请求异常: {e}")

            data = ENGINE.load_accounts()
            all_accounts = data.get("accounts", {})
            selected_dict = {}
            for e in target_emails:
                if e in all_accounts:
                    selected_dict[e] = all_accounts[e]

            export_payload = {
                "exported_at": datetime.datetime.now().isoformat(),
                "generator": f"Antigravity Hub v{__version__}",
                "count": len(selected_dict),
                "accounts": selected_dict
            }
            resp_bytes = json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8")
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"antigravity_selected_accounts_{now_str}.json"

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(resp_bytes)
            logger.info(f"📦 [批量导出] 已成功导出 {len(selected_dict)} 个账号凭据")
            return

        elif parsed.path == "/api/delete_accounts":
            target_emails = []
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    target_emails = req_j.get("emails", [])
                else:
                    target_emails = params.get("emails[]", params.get("emails", []))
            except Exception as e:
                logger.error(f"解析 delete_accounts 请求异常: {e}")

            data = ENGINE.load_accounts()
            active_email = data.get("active_email", "")
            accounts = data.get("accounts", {})

            # 🛡️ 物理最高门禁：拦截当前正在使用的护航活跃账号
            deletable_emails = [e for e in target_emails if e in accounts and e != active_email]

            if deletable_emails:
                # 自动灾备归档留痕
                archive_file = os.path.join(os.path.dirname(ACCOUNTS_HUB_FILE), "deleted_accounts_archive.json")
                archived_data = {}
                if os.path.exists(archive_file):
                    try:
                        with open(archive_file, "r", encoding="utf-8") as af:
                            archived_data = json.load(af)
                    except Exception:
                        archived_data = {}

                now_iso = datetime.datetime.now().isoformat()
                for e in deletable_emails:
                    rec = accounts.pop(e)
                    rec["deleted_at"] = now_iso
                    archived_data[e] = rec

                try:
                    with open(archive_file, "w", encoding="utf-8") as af:
                        json.dump(archived_data, af, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"归档已删除账号数据异常: {e}")

                # 保存更新后的账号池
                data["accounts"] = accounts
                ENGINE.save_accounts(data)

                # 同步清理持久化顺序列表 (若存在)
                order_file = os.path.join(os.path.dirname(ACCOUNTS_HUB_FILE), "accounts_order.json")
                if os.path.exists(order_file):
                    try:
                        with open(order_file, "r", encoding="utf-8") as of:
                            cur_order = json.load(of)
                        if isinstance(cur_order, list):
                            new_order = [x for x in cur_order if x not in deletable_emails]
                            with open(order_file, "w", encoding="utf-8") as of:
                                json.dump(new_order, of, ensure_ascii=False, indent=2)
                    except Exception:
                        pass

                logger.info(f"🗑️ [批量安全删除] 成功从账号池切除并归档 {len(deletable_emails)} 个账号: {deletable_emails}")

            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
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
        logger.info("后台状态同步已启动 (15s 本地 language_server 实时同步 + 3m 全池配额校准)")
        try:
            ENGINE.refresh_all_quotas()
        except Exception as e:
            logger.warning(f"启动初始配额同步异常: {e}")
        finally:
            ENGINE._initial_quota_sync_done.set()
        last_full_refresh = time.time()
        while True:
            try:
                time.sleep(15)
                ENGINE.sync_from_local_language_server()
                now_t = time.time()
                if now_t - last_full_refresh >= 180:
                    last_full_refresh = now_t
                    ENGINE.refresh_all_quotas()
            except Exception as e:
                logger.error(f"后台本地配额同步异常: {e}")

    def warmup_worker():
        logger.info("后台每小时智能随机错峰预热守卫已启动 (5h 真实 1-token 激活与到期续热)")
        # 等待首次全池官方配额探测与三档分类完成（最多 15s）后再启动排班
        ENGINE._initial_quota_sync_done.wait(timeout=15)
        last_global_round = 0
        from core.switcher import AntigravityPhysicalManager
        mgr = AntigravityPhysicalManager()
        while True:
            try:
                cfg = get_hub_settings()
                if cfg.get("hourly_warmup", True):
                    warmup_mode = str(cfg.get("warmup_model") or "dual")
                    stagger_sec = int(cfg.get("warmup_stagger_sec") or 60)
                    now = int(time.time())
                    # 每小时触发一次全池随机错峰排班校准 (3300 至 3900 秒随机抖动)
                    is_hourly_round = (now - last_global_round >= random.randint(3300, 3900))
                    if is_hourly_round or last_global_round == 0:
                        last_global_round = now
                        logger.info("⏰ [定时触发] 每小时全局随机错峰预热巡检启动！")
                        ENGINE.run_hourly_staggered_warmup(force=False)
                    else:
                        # 高频巡检 (30s)：触发已到达随机排班时刻的 PRO 账号执行真实 1-token 预热
                        mgr.check_and_trigger_due_staggered_warmup(
                            stagger_sec=stagger_sec, warmup_mode=warmup_mode
                        )

                time.sleep(30)
            except Exception as e:
                logger.error(f"后台预热调度异常: {e}")
                time.sleep(30)

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
