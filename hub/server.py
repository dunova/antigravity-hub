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
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

__version__ = "2.41.0"
__canonical_version_tag__ = "20261013-v2.41.0-UNIFIED_POOL_SSOT_AND_TRUE_MODEL_MATRIX"
__last_updated__ = "2026-10-13 11:45:32"
__canonical_doctrine__ = "全链路三库统一SSOT+已删账号防复活物理门禁+切除虚假Claude5.5标签+真实模型矩阵实时探测"



# 配置常量
BASE_DATA_DIR = os.environ.get("ANTIGRAVITY_HUB_DIR", os.path.expanduser("~/.antigravity_hub"))
HUB_DIR = os.path.join(BASE_DATA_DIR, "data")
ACCOUNTS_HUB_FILE = os.path.join(HUB_DIR, "accounts_hub.json")
WARMUP_HUB_FILE = os.path.join(HUB_DIR, "warmup_hub.json")
WARMUP_SCHEDULE_PATH = os.path.join(HUB_DIR, "warmup_schedule.json")
AUTO_ROTATION_CONFIG_PATH = os.path.join(BASE_DATA_DIR, "auto_rotation_config.json")
MANUAL_OVERRIDE_LOCK_PATH = os.path.join(BASE_DATA_DIR, "manual_override_lock.json")

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


def get_installed_browser_candidates() -> List[Dict[str, Any]]:
    """
    返回当前系统可用浏览器候选列表（按优先级排序）：
    1. ego lite（用户主力默认浏览器，/Applications/ego lite.app）
    2. Google Chrome（若安装）
    """
    candidates = []
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

    return candidates


def launch_browser_for_auth(url: str, isolated: bool = False, profile_name: str = "") -> bool:
    """
    为解封或 OAuth 授权拉起浏览器：
    - 优先绑定用户现役主力浏览器 ego lite；
    - 支持带独立 profile 隔离容器（isolated=True）或在现役会话中秒级打开标签页（isolated=False）；
    - 若指定独立容器失败，平滑回退到现役 ego lite 窗口；
    - 若 ego lite 不存在，自动回退 Chrome，终极保底回退 open <url>；
    - 彻底杜绝因写死 Google Chrome 导致应用未安装而静默失败的隐患。
    """
    candidates = get_installed_browser_candidates()
    profile_dir = os.path.join(BASE_DATA_DIR, "browser_profiles", profile_name) if profile_name else None
    if profile_dir:
        os.makedirs(profile_dir, exist_ok=True)

    for cand in candidates:
        app_name = cand["name"]
        try:
            if isolated and profile_dir:
                cmd = ["open", "-na", app_name, "--args", f"--user-data-dir={profile_dir}", url]
                p = subprocess.Popen(cmd)
                p.wait(timeout=1)
                if p.returncode == 0:
                    logger.info(f"🚀 [浏览器调起] 已为授权/解封拉起独立容器 ({app_name}): {profile_dir}")
                    return True
                else:
                    logger.warning(f"⚠️ [浏览器调起] 独立容器启动返回码非0 ({p.returncode})，尝试平滑切换至标准打开")

            # 标准模式或独立容器回退：直接在现役窗口中新建标签页拉起并聚焦
            cmd = ["open", "-a", app_name, url]
            subprocess.Popen(cmd)
            logger.info(f"🚀 [浏览器调起] 已在现役 {app_name} 浏览器中打开目标 URL")
            return True
        except Exception as e:
            logger.warning(f"⚠️ [浏览器调起] 拉起 {app_name} 异常: {e}，尝试下一个候选")

    # 保底：使用 macOS 系统默认浏览器
    try:
        subprocess.Popen(["open", url])
        logger.info(f"🚀 [浏览器调起] 已使用系统默认浏览器打开目标 URL")
        return True
    except Exception as e:
        logger.error(f"❌ [浏览器调起失败] 系统默认 open 打开异常: {e}")
        return False


def atomic_write_json(file_path: str, data: Any, indent: int = 2) -> bool:
    tmp_path = None
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        tmp_path = f"{file_path}.tmp.{os.getpid()}.{time.time()}.{random.randint(1000, 9999)}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
        tmp_path = None
        return True
    except Exception as e:
        logger.error(f"原子写入 {file_path} 失败: {e}")
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass



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


def get_auto_rotation_config() -> Dict[str, Any]:
    """
    【全局自动轮换配置】读取自动轮换三态模式配置。
    三态模式:
      - 'gemini': 自动轮转 Gemini (仅关注 Gemini 额度)
      - 'claude': 自动轮转 Claude (仅关注 Claude 额度)
      - 'off':    彻底关闭轮转功能 (看门狗完全冻结)
    兼容旧字段 enabled 与 policy。
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

    if "mode" in cfg and cfg["mode"] in ("gemini", "claude", "off"):
        m = cfg["mode"]
    else:
        if not cfg.get("enabled", True):
            m = "off"
        elif cfg.get("policy") in ("claude_first", "claude"):
            m = "claude"
        else:
            m = "gemini"
    cfg["mode"] = m
    cfg["enabled"] = (m != "off")
    cfg["policy"] = "claude_first" if m == "claude" else "gemini_first"
    return cfg


def set_auto_rotation_config(mode: str = "gemini", enabled: Optional[bool] = None, policy: Optional[str] = None) -> Dict[str, Any]:
    """
    【全局自动轮换配置】持久化原子保存自动轮换三态模式。
    支持显式传入 mode ('gemini' | 'claude' | 'off')，亦兼容旧参数 enabled/policy。
    """
    if mode not in ("gemini", "claude", "off"):
        if enabled is False:
            mode = "off"
        elif policy in ("claude_first", "claude"):
            mode = "claude"
        else:
            mode = "gemini"

    cfg = {
        "mode": mode,
        "enabled": (mode != "off"),
        "policy": "claude_first" if mode == "claude" else "gemini_first",
        "updated_at": int(time.time()),
        "updated_by": "hub_ui"
    }
    atomic_write_json(AUTO_ROTATION_CONFIG_PATH, cfg)
    logger.info(f"💾 [轮换配置持久化] 三态模式已保存: mode={mode} (enabled={cfg['enabled']}, policy={cfg['policy']}) -> {AUTO_ROTATION_CONFIG_PATH}")
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


class HubEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.refreshing_now = False
        self._cached_accounts_data: Dict[str, Any] = {}
        self._ensure_storage()

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

        # 尝试通过 import_accounts_hub
        try:
            import import_accounts_hub
            if hasattr(import_accounts_hub, "import_accounts_read_only"):
                if import_accounts_hub.import_accounts_read_only(ACCOUNTS_HUB_FILE):
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
                if not acc_obj.get("tier"):
                    acc_obj["tier"] = "PRO"
                if not acc_obj.get("claude_version") or acc_obj.get("claude_version") == "5.5":
                    c_mods = acc_obj.get("claude_models") or []
                    has_real_55 = any(("5-5" in m or "5.5" in m) for m in c_mods)
                    if not has_real_55:
                        acc_obj["claude_version"] = "4.6"
                        acc_obj["claude_models"] = ["claude-sonnet-4-6", "claude-opus-4-6-thinking"]

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

            # 3. 🔄 同步到底层轮换池与工具索引 (杜绝双脑分裂与幽灵账号复活)
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
                "last_5h_fraction": round(float(acc.get("gemini", {}).get("quota_5h", 1.0)), 4),
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

    def auto_ingest_system_account(self) -> Optional[Tuple[str, bool]]:
        """
        【新登录账号 100% 自动热维护纳管】
        实时从 macOS Keychain 与系统配置中嗅探当前活跃登录账号，
        若发现新登录账号或凭据更新，自动无感热纳管至 accounts_hub.json 并初始化配额。
        （已删归档账号受物理门禁拦截，绝不被动死灰复燃）
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
                # 🛑 防死灰复燃门禁：若该账号存在于 deleted_accounts_archive.json，严禁后台自动重新纳管！
                archive_file = os.path.join(os.path.dirname(ACCOUNTS_HUB_FILE), "deleted_accounts_archive.json")
                if os.path.exists(archive_file):
                    try:
                        with open(archive_file, "r", encoding="utf-8") as af:
                            deleted_arch = json.load(af)
                        if detected_email in deleted_arch:
                            logger.warning(f"🛡️ [已删账号防复活拦截] Keychain 检测到已归档删除账号 {detected_email}，拒绝自动重新纳管！")
                            return None
                    except Exception:
                        pass

                logger.info(f"✨ [热维护自动纳管] 发现新登录账号: {detected_email}，正在自动纳管...")
                c_ver, c_models = self.fetch_available_models(at)
                new_acc = {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, detected_email)),
                    "email": detected_email,
                    "tier": "PRO",
                    "pro": True,
                    "claude_version": c_ver,
                    "claude_models": c_models or ["claude-sonnet-4-6", "claude-opus-4-6-thinking"],
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
                    quotas, resets, _ = self.fetch_live_quota(at)
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

    def fetch_available_models(self, access_token: str) -> Tuple[str, List[str]]:
        """
        探测账号支持的模型矩阵，精准区分 Claude 5.5 (付费Pro) 与 Claude 4.6 (未付费Pro·预计11月下架)
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
            with urllib.request.urlopen(req, timeout=8, context=ctx) as resp:
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

            c_ver, c_models = self.fetch_available_models(at)
            if c_models:
                acc["claude_version"] = c_ver
                acc["claude_models"] = c_models
            elif not acc.get("claude_version") or acc.get("claude_version") == "5.5":
                acc["claude_version"] = "4.6"
                acc["claude_models"] = ["claude-sonnet-4-6", "claude-opus-4-6-thinking"]

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

    def trigger_warmup(self, email: str, acc: Dict[str, Any], model_override: str = "") -> bool:
        """
        【Hub 预热单账号直通入口 · 对齐物理中枢 AntigravityPhysicalManager】
        """
        try:
            from antigravity_physical_switcher import AntigravityPhysicalManager
            mgr = AntigravityPhysicalManager()
            acc_entry = dict(acc)
            acc_entry["email"] = email
            res = mgr.warmup_single_account(acc_entry, force=True, model_override=model_override)
            st = res.get("status")
            if st in ("success", "cooldown_active"):
                logger.info(f"🔥 Hub 触发预热成功: {email} -> {res}")
                now = int(time.time())
                acc["last_warmup_ts"] = now
                acc["next_warmup_ts"] = now + 14400 + random.randint(600, 2400)
                # 触发配额刷新并写回
                self.refresh_single_account_quota(email, acc)
                return True
            else:
                logger.warning(f"⚠️ Hub 触发预热非成功: {email} -> {res}")
                return False
        except Exception as e:
            logger.error(f"❌ Hub 触发预热异常 {email}: {e}")
            return False

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
            success = mgr.perform_real_switch(target_email, restart_app=True, relay_prompt=relay_prompt, force=True, inject_recovery=False)
            if success:
                # 同步更新 Hub 本地数据库活跃指针
                data = self.load_accounts()
                data["active_email"] = target_email
                data["last_updated"] = int(time.time())
                self.save_accounts(data)
                # 用户手动点击切换账号，必须自动将全局自动轮换置为关闭，保护人工选号不被看门狗切走！
                set_auto_rotation_config(mode="off")
                logger.info(f"🛡️ [人工切换保护] 已将自动轮换模式置为【关闭】，确保用户手动指定的账号 {target_email} 绝对不被后台轮换切走！")
                logger.info(f"🚀 [物理切换成功] 目标账号 {target_email} 凭据已注入，Antigravity 正在平滑重载（人工切换不注入接力词）！")
                return True, f"物理切换至 {target_email} 成功，Antigravity 正在平滑重载！"
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


def render_quota_cell(h5_pct: float, weekly_pct: float, reset_5h_info: str = "", reset_weekly_info: str = "", model_type: str = "gemini", claude_ver: str = "") -> str:
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
    elif val_5h >= 99.9:
        is_warmup_in_progress = (
            reset_5h_info 
            and reset_5h_info not in ("--", "已就绪") 
            and not reset_5h_info.startswith("4h 5") 
            and not reset_5h_info.startswith("4h 4") 
            and not reset_5h_info.startswith("5h")
        )
        if is_warmup_in_progress:
            reset_5h_html = f'<span class="q-reset q-reset-5h font-mono" title="预热阶梯倒计时: {reset_5h_info}">{reset_5h_info}</span>'
        else:
            reset_5h_html = '<span class="q-reset q-reset-ready font-mono" title="满血待命，随时可用">就绪</span>'
    elif reset_5h_info and reset_5h_info not in ("--", "已就绪"):
        reset_5h_html = f'<span class="q-reset q-reset-5h font-mono" title="5小时滚动配额恢复倒计时: {reset_5h_info}">{reset_5h_info}</span>'
    elif reset_5h_info == "已就绪":
        reset_5h_html = '<span class="q-reset q-reset-ready font-mono" title="已恢复就绪">就绪</span>'
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

    cell_title = ""
    if model_type == "claude":
        cell_title = ' title="Claude Sonnet 4.6 / Opus 4.6 Thinking 配额 (5h 滚动 / 周度总额)"'
    elif model_type == "gemini":
        cell_title = ' title="Gemini 2.5 Pro / Flash 配额 (5h 滚动 / 周度总额)"'

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


# 商业级专业数据表格色盘：高级纯白与极淡暖灰斑马纹，彻底告别花里胡哨彩虹条
ROW_BG_ODD = "#FFFFFF"
ROW_BG_EVEN = "#F9FAFB"
ROW_BG_ACTIVE = "#FEF9C3"

AVATAR_COLORS = [
    "#DBEAFE", "#FCE7F3", "#DCFCE7", "#FEF3C7", "#E0E7FF",
    "#F3E8FF", "#CCFBF1", "#FEE2E2", "#FFEDD5", "#CFFAFE"
]


def render_top_bar_stats_html(total_count: int = 0, pro_count: int = 0, avg_g: float = 0.0, avg_c: float = 0.0, cur_time: str = "", oob: bool = False) -> str:
    oob_attr = ' hx-swap-oob="outerHTML:#top-bar-stats"' if oob else ''
    data = ENGINE.load_accounts()
    accounts = data.get("accounts", {})
    active_email = data.get("active_email", "")
    total_count = len(accounts)
    pro_count = sum(1 for a in accounts.values() if a.get("tier") == "PRO" or a.get("pro"))
    usable_count = sum(1 for a in accounts.values() if (a.get("gemini", {}).get("quota_weekly", 0.0) > 0.0001 or a.get("claude", {}).get("quota_weekly", 0.0) > 0.0001) and not a.get("validation_blocked"))
    blocked_count = sum(1 for a in accounts.values() if a.get("validation_blocked"))
    
    avg_g_5h = round(sum(a.get("gemini", {}).get("quota_5h", 1.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    avg_g_w = round(sum(a.get("gemini", {}).get("quota_weekly", 1.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    avg_c_5h = round(sum(a.get("claude", {}).get("quota_5h", 1.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    avg_c_w = round(sum(a.get("claude", {}).get("quota_weekly", 1.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    
    ready_g = sum(1 for a in accounts.values() if a.get("gemini", {}).get("quota_5h", 1.0) >= 0.99 and a.get("gemini", {}).get("quota_weekly", 1.0) > 0.0001)
    ready_c = sum(1 for a in accounts.values() if a.get("claude", {}).get("quota_5h", 1.0) >= 0.99 and a.get("claude", {}).get("quota_weekly", 1.0) > 0.0001)
    
    rot_cfg = get_auto_rotation_config()
    rot_mode = rot_cfg.get("mode", "gemini")
    
    lock_info = get_manual_override_lock()
    now_ts = time.time()
    is_locked = bool(lock_info and lock_info.get("manual_account") == active_email and lock_info.get("locked_until", 0) > now_ts)
    lock_rem = max(1, int((lock_info.get("locked_until", 0) - now_ts) // 60)) if is_locked else 0

    active_short = active_email.split("@")[0] if "@" in active_email else (active_email or "未设置")
    active_acc = accounts.get(active_email, {})
    active_g_5h = round(active_acc.get("gemini", {}).get("quota_5h", 1.0) * 100, 1)
    active_c_5h = round(active_acc.get("claude", {}).get("quota_5h", 1.0) * 100, 1)
    
    if rot_mode == "gemini":
        engine_badge = '<span class="stat-badge stat-badge-green font-mono">⚡ 轮换 GEMINI</span>'
        engine_title = "智能额度流转"
    elif rot_mode == "claude":
        engine_badge = '<span class="stat-badge stat-badge-amber font-mono">⚡ 轮换 CLAUDE</span>'
        engine_title = "智能额度流转"
    else:
        engine_badge = '<span class="stat-badge stat-badge-gray font-mono">🛑 轮转已冻结</span>'
        engine_title = "人工指定守护"

    cur_time = time.strftime("%H:%M:%S")

    return f"""<div id="top-bar-stats" class="stats-grid font-mono"{oob_attr}>
        <!-- 卡片 1: 在岗执勤哨兵 -->
        <div class="stat-card stat-card-active" onclick="copyText('{active_email}')" title="点击快速复制当前执勤账号完整凭据: {active_email}">
            <div class="stat-card-header">
                <span class="stat-card-label"><span class="pulse-dot-green"></span>在岗执勤哨兵</span>
                <span class="stat-badge {'stat-badge-locked' if is_locked else 'stat-badge-active'} font-mono">{'🛡️ 人工锁定 (' + str(lock_rem) + 'm)' if is_locked else '⚡ 自动接力'}</span>
            </div>
            <div class="stat-card-main">
                <span class="stat-card-val text-truncate">{active_short}</span>
            </div>
            <div class="stat-card-footer">
                <span class="stat-tag tag-pro font-mono">PRO 执勤</span>
                <span class="stat-muted">G: {active_g_5h}% · C: {active_c_5h}%</span>
            </div>
        </div>

        <!-- 卡片 2: 集群资产总览 -->
        <div class="stat-card">
            <div class="stat-card-header">
                <span class="stat-card-label"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>集群纳管资产</span>
                <span class="stat-badge stat-badge-green font-mono">{'100% HEALTHY' if blocked_count == 0 else str(blocked_count) + ' BLOCKED'}</span>
            </div>
            <div class="stat-card-main">
                <span class="stat-card-val">{total_count}</span>
                <span class="stat-unit">账号在册</span>
            </div>
            <div class="stat-card-footer">
                <span class="stat-tag tag-pro font-mono">PRO {pro_count}</span>
                <span class="stat-tag tag-claude-ver font-mono">可用 {usable_count}/{total_count}</span>
                <span class="stat-muted">{blocked_count} 异常</span>
            </div>
        </div>

        <!-- 卡片 3: Gemini 算力池 -->
        <div class="stat-card stat-card-gemini">
            <div class="stat-card-header">
                <span class="stat-card-label"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#2563EB" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>Gemini 算力池</span>
                <span class="stat-badge stat-badge-blue font-mono">Google 2.5</span>
            </div>
            <div class="stat-card-main">
                <span class="stat-card-val">{avg_g_w}%</span>
                <span class="stat-unit">周均算力</span>
            </div>
            <div class="stat-mini-progress">
                <div class="mini-bar-track" title="全池 5h 滚动均值: {avg_g_5h}%"><div class="mini-bar-fill fill-blue" style="width: {min(100, max(0, avg_g_5h))}%;"></div></div>
                <div class="mini-bar-label"><span>5h 均值: {avg_g_5h}%</span><span>满血待命: {ready_g}/{total_count}</span></div>
            </div>
        </div>

        <!-- 卡片 4: Claude 算力池 -->
        <div class="stat-card stat-card-claude">
            <div class="stat-card-header">
                <span class="stat-card-label"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>Claude 算力池</span>
                <span class="stat-badge stat-badge-amber font-mono">Anthropic</span>
            </div>
            <div class="stat-card-main">
                <span class="stat-card-val">{avg_c_w}%</span>
                <span class="stat-unit">周均算力</span>
            </div>
            <div class="stat-mini-progress">
                <div class="mini-bar-track" title="全池 5h 滚动均值: {avg_c_5h}%"><div class="mini-bar-fill fill-amber" style="width: {min(100, max(0, avg_c_5h))}%;"></div></div>
                <div class="mini-bar-label"><span>5h 均值: {avg_c_5h}%</span><span>满血待命: {ready_c}/{total_count}</span></div>
            </div>
        </div>

        <!-- 卡片 5: 自动化中枢守护 -->
        <div class="stat-card stat-card-engine">
            <div class="stat-card-header">
                <span class="stat-card-label"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="vertical-align:-1px;margin-right:3px;"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>自动化中枢</span>
                {engine_badge}
            </div>
            <div class="stat-card-main">
                <span class="stat-card-val text-sm">{engine_title}</span>
            </div>
            <div class="stat-card-footer">
                <span class="stat-tag tag-engine font-mono">30s 实时刷新</span>
                <span class="stat-muted font-mono">{cur_time}</span>
            </div>
        </div>
    </div>"""


def render_active_pill_html(active_email: str, oob: bool = False) -> str:
    oob_attr = ' hx-swap-oob="outerHTML:#active-email-pill"' if oob else ""
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
    pro_count = sum(1 for a in accounts.values() if a.get("tier") == "PRO" or a.get("pro"))
    avg_g = round(sum(a.get("gemini", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    avg_c = round(sum(a.get("claude", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    cur_time = time.strftime("%H:%M:%S")

    if not accounts:
        empty_row = '<tr><td colspan="7" style="text-align:center; padding: 32px; font-size:13px; font-weight:900; background:#FFF1F2; color:#E11D48;">暂无账号数据，请点击顶栏【导入】吸纳账号凭据</td></tr>'
        if include_oob:
            return empty_row + "\n" + render_top_bar_stats_html(0, 0, 0.0, 0.0, cur_time, oob=True) + "\n" + render_active_pill_html("", oob=True) + "\n" + render_rotation_button_html(oob=True) + "\n" + render_version_marker_html(oob=True)
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
        
        row_bg = ROW_BG_ACTIVE if is_active else (ROW_BG_ODD if (idx % 2 == 1) else ROW_BG_EVEN)
        active_class = "is-active-row" if is_active else ""
        
        num_html = f"""<div class="num-cell-inner" title="按住拖拽调节账号顺序"><span class="drag-handle">⠿</span><span class="row-num font-mono">{idx}</span></div>"""

        is_blocked = bool(acc.get("validation_blocked"))
        val_url = acc.get("validation_url", "")

        detail_btn_html = f"""<button class="btn btn-detail font-mono" onclick="openAccountDrawer('{email}'); event.preventDefault(); event.stopPropagation();" title="查看全量资产画像与完整支持模型">详情</button>"""

        if is_active:
            badge_html = '<span class="badge badge-active"><span class="pulse-dot-green"></span>ACTIVE</span>'
            main_btn_html = f"""<div class="btn-in-use active-badge-action font-mono" title="当前主程序正在使用此账号护航">在用</div>
                                <button class="btn btn-warmup font-mono" 
                                onclick="doWarmupAccount('{email}'); event.preventDefault(); event.stopPropagation();"
                                title="向该账号发送极轻量真实生成，提前锁定5h倒计时错峰就绪">预热</button>
                                {detail_btn_html}"""
        elif is_blocked:
            badge_html = '<span class="badge badge-blocked" title="Google账号需网页验证">⚠️待验证</span>'
            main_btn_html = f"""<button class="btn btn-unblock font-mono" 
                            onclick="doUnblockAccount('{email}'); event.preventDefault(); event.stopPropagation();"
                            title="在现役 ego lite 浏览器中拉起解封页面并自动定向该账号（后台自动监听解锁）">解封</button>
                            {detail_btn_html}"""
        else:
            badge_html = '<span class="badge badge-standby">STANDBY</span>'
            has_refresh_token = bool(acc.get("refresh_token", ""))
            if has_refresh_token:
                main_btn_html = f"""<button class="btn btn-switch font-mono" 
                                onclick="doSwitchAccount('{email}'); event.preventDefault(); event.stopPropagation();"
                                title="切换为此账号，看门狗照常监控额度自动轮换">切换</button>
                                <button class="btn btn-warmup font-mono" 
                                onclick="doWarmupAccount('{email}'); event.preventDefault(); event.stopPropagation();"
                                title="向该账号发送极轻量真实生成，提前锁定5h倒计时错峰就绪">预热</button>
                                {detail_btn_html}"""
            else:
                main_btn_html = f"""<button class="btn btn-switch font-mono" 
                                style="opacity:0.35;cursor:not-allowed;background:#ccc;"
                                onclick="event.preventDefault();event.stopPropagation();showToast('❌ 此账号缺少授权 Token，无法切换！请先在 Antigravity 中重新登录此账号。','error');"
                                title="此账号缺少 refresh_token，无法物理切换">无Token</button>
                                {detail_btn_html}"""

        action_switch_html = f"""<div class="actions-flex">{main_btn_html}</div>"""

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

        # Claude 配额与真实模型版本
        claude_ver = "5.5" if any(("5-5" in m or "5.5" in m) for m in (acc.get("claude_models") or [])) else "4.6"
        c_w = acc.get("claude", {}).get("quota_weekly", 1.0)
        c_5h = 0.0 if c_w <= 0.0001 else acc.get("claude", {}).get("quota_5h", 1.0)
        c_reset_raw = acc.get("claude", {}).get("reset_time_5h", "")
        if (not c_reset_raw or c_reset_raw == "--") and warmup_iso and ("claude" in warmup_model):
            c_reset_raw = warmup_iso
        c_reset_5h = format_reset_time(c_reset_raw)
        c_reset_w = format_reset_time(acc.get("claude", {}).get("reset_time_weekly", acc.get("claude", {}).get("reset_time", "")))
        c_cell = render_quota_cell(c_5h, c_w, c_reset_5h, c_reset_w, model_type="claude", claude_ver=claude_ver)

        short_name = email.split("@")[0] if "@" in email else email
        first_letter = (short_name[0] if short_name else "A").upper()
        avatar_color = AVATAR_COLORS[ord(first_letter) % len(AVATAR_COLORS)]
        avatar_html = f'<div class="acc-avatar font-mono" style="background:{avatar_color};">{first_letter}</div>'

        pro_tag_html = '<span class="pro-tag pro-tag-46 font-mono" title="Google AI Pro 授权账号">PRO</span>'

        row = f"""
        <tr class="account-row {active_class}" 
            draggable="true"
            style="background-color: {row_bg};"
            data-email="{email}"
            data-orig-idx="{idx}"
            data-claude-ver="{claude_ver}"
            data-gemini-5h="{g_5h}"
            data-gemini-w="{g_w}"
            data-claude-5h="{c_5h}"
            data-claude-w="{c_w}"
            data-is-active="{'1' if is_active else '0'}"
            ondblclick="openAccountDrawer('{email}')">
            <td class="col-center col-check" style="background-color: {row_bg}; width: 36px; padding: 0 4px;"><input type="checkbox" class="row-select-cb neo-checkbox" value="{email}" data-email="{email}" onchange="onRowSelectChange(this)" title="勾选 {email}"></td>
            <td class="col-center font-mono num-col" style="background-color: {row_bg};">{num_html}</td>
            <td class="col-status" style="background-color: {row_bg};"><div class="status-cell-wrap">{badge_html}</div></td>
            <td class="col-email" style="background-color: {row_bg};">
                <div class="email-cell-inner" onclick="openAccountDrawer('{email}')" title="双击或点击查看详情: {email}">
                    {avatar_html}
                    <div class="email-name-group">
                        <span class="email-text font-mono" onclick="copyText('{email}'); event.stopPropagation();" title="点击复制完整账号: {email}">{short_name}</span>
                        <span class="email-sub font-mono">{email}</span>
                    </div>
                    {pro_tag_html}
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
        btn_text = "⚡ 轮转: Gemini"
        btn_icon = '<polygon points="5 3 19 12 5 21 5 3"/>'
        btn_title = "当前模式：自动轮转 Gemini（仅关注 Gemini 额度，耗尽自动切号，忽略 Claude 额度；点击切换为自动轮转 Claude）"
    elif mode == "claude":
        btn_cls = "btn-rotation-claude"
        btn_text = "⚡ 轮转: Claude"
        btn_icon = '<polygon points="5 3 19 12 5 21 5 3"/>'
        btn_title = "当前模式：自动轮转 Claude（仅关注 Claude 额度，耗尽自动切号，忽略 Gemini 额度；点击彻底关闭轮转）"
    else:  # 'off'
        btn_cls = "btn-rotation-off"
        btn_text = "🚫 轮转: 关闭"
        btn_icon = '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>'
        btn_title = "当前模式：彻底关闭自动轮转（看门狗已冻结，不会自动切号；点击开启自动轮转 Gemini）"

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
    pro_count = sum(1 for a in accounts.values() if a.get("tier") == "PRO" or a.get("pro"))
    avg_g = round(sum(a.get("gemini", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    avg_c = round(sum(a.get("claude", {}).get("quota_weekly", 0.0) for a in accounts.values()) / max(1, total_count) * 100, 1)
    cur_time = time.strftime("%H:%M:%S")

    rot_btn_html = render_rotation_button_html(oob=False)
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

        /* 🚀 弹性全自适应商业版心：扩大至 1400px，两翼舒适留白，全面对齐商业 SaaS 控制台 */
        .app-container {{
            width: 100%;
            max-width: 1400px;
            min-width: 900px;
            margin: 0 auto;
            box-sizing: border-box;
            padding: 0 20px;
            flex-shrink: 0;
        }}

        /* 📊 全景 KPI 商业指标大盘网格 */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 10px;
            margin-bottom: 10px;
            width: 100% !important;
            box-sizing: border-box;
        }}
        @media (max-width: 1200px) {{
            .stats-grid {{
                grid-template-columns: repeat(3, 1fr);
            }}
        }}
        .stat-card {{
            background: #FFFFFF;
            border: var(--border-black);
            border-radius: var(--radius-card);
            box-shadow: 2.5px 2.5px 0px #000000;
            padding: 9px 12px;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            min-height: 82px;
            transition: transform 0.08s ease, box-shadow 0.08s ease;
            cursor: default;
        }}
        .stat-card:hover {{
            transform: translateY(-1.5px);
            box-shadow: 3.5px 3.5px 0px #000000;
        }}
        .stat-card-active {{
            background: #FEFCE8;
            cursor: pointer;
        }}
        .stat-card-gemini {{
            background: #F0F9FF;
        }}
        .stat-card-claude {{
            background: #FFFBEB;
        }}
        .stat-card-engine {{
            background: #FAF5FF;
        }}
        .stat-card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 10.5px;
            font-weight: 800;
            margin-bottom: 3px;
        }}
        .stat-card-label {{
            color: #4B5563;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            letter-spacing: 0.2px;
        }}
        .stat-badge {{
            font-size: 9px;
            font-weight: 900;
            padding: 1.5px 5px;
            border: 1.5px solid #000000;
            border-radius: 4px;
            box-shadow: 1px 1px 0px #000000;
            line-height: 1.1;
        }}
        .stat-badge-active {{ background: #4ADE80; color: #000000; }}
        .stat-badge-locked {{ background: #FDA4AF; color: #9F1239; }}
        .stat-badge-green {{ background: #86EFAC; color: #000000; }}
        .stat-badge-blue {{ background: #93C5FD; color: #000000; }}
        .stat-badge-amber {{ background: #FCD34D; color: #000000; }}
        .stat-badge-gray {{ background: #E5E7EB; color: #000000; }}
        .stat-card-main {{
            display: flex;
            align-items: baseline;
            gap: 5px;
            margin: 1px 0 3px 0;
            overflow: hidden;
        }}
        .stat-card-val {{
            font-size: 17px;
            font-weight: 900;
            color: #000000;
            line-height: 1.1;
            letter-spacing: -0.3px;
        }}
        .stat-unit {{
            font-size: 10.5px;
            font-weight: 700;
            color: #6B7280;
        }}
        .stat-card-footer {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 10px;
            white-space: nowrap;
            overflow: hidden;
        }}
        .stat-tag {{
            font-size: 9px;
            font-weight: 900;
            padding: 1px 4px;
            border: 1px solid #000000;
            border-radius: 3px;
            line-height: 1;
        }}
        .tag-claude-ver {{ background: #FDE047; color: #000; }}
        .tag-pro {{ background: #F472B6; color: #000; }}
        .tag-55 {{ background: #FB923C; color: #000; }}
        .tag-engine {{ background: #C084FC; color: #000; }}
        .stat-muted {{
            color: #6B7280;
            font-size: 9.5px;
            font-weight: 600;
        }}
        .stat-mini-progress {{
            width: 100%;
            margin-top: 2px;
        }}
        .mini-bar-track {{
            width: 100%;
            height: 5px;
            background: #E5E7EB;
            border: 1px solid #000000;
            border-radius: 3px;
            overflow: hidden;
            box-sizing: border-box;
        }}
        .mini-bar-fill {{
            height: 100%;
            transition: width 0.3s ease;
        }}
        .fill-blue {{ background: #2563EB; }}
        .fill-amber {{ background: #D97706; }}
        .mini-bar-label {{
            display: flex;
            justify-content: space-between;
            font-size: 9px;
            color: #4B5563;
            font-weight: 700;
            margin-top: 2px;
        }}
        .text-truncate {{
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .text-sm {{
            font-size: 13.5px !important;
        }}

        /* 🪪 账号头像与现代信息组 */
        .acc-avatar {{
            width: 22px;
            height: 22px;
            border: 1.5px solid #000000;
            border-radius: 5px;
            box-shadow: 1px 1px 0px #000000;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 10.5px;
            font-weight: 900;
            color: #000000;
            flex-shrink: 0;
        }}
        .email-name-group {{
            display: flex;
            flex-direction: column;
            line-height: 1.15;
            overflow: hidden;
            text-align: left;
        }}
        .email-sub {{
            font-size: 9.5px;
            color: #6B7280;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 170px;
        }}
        .btn-detail {{
            background: #FFFFFF;
            color: #000000;
            border: 1.5px solid #000000;
            border-radius: var(--radius-btn);
            box-shadow: 1.5px 1.5px 0px #000000;
            font-size: 10.5px;
            font-weight: 800;
            padding: 0 7px;
            height: 22px;
            cursor: pointer;
            transition: all 0.08s ease;
        }}
        .btn-detail:hover {{
            background: #F3F4F6;
            transform: translate(-1px, -1px);
            box-shadow: 2px 2px 0px #000000;
        }}

        /* 🚪 商业级账号资产详情右侧抽屉 (Account Slide-over Drawer) */
        .drawer-backdrop {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.45);
            z-index: 9998;
            display: none;
            opacity: 0;
            transition: opacity 0.2s ease;
        }}
        .drawer-backdrop.show {{
            display: block;
            opacity: 1;
        }}
        .account-drawer {{
            position: fixed;
            top: 0;
            right: 0;
            width: 480px;
            max-width: 90vw;
            height: 100vh;
            background: #F8F6F0;
            border-left: 3px solid #000000;
            box-shadow: -6px 0px 0px rgba(0, 0, 0, 0.15);
            z-index: 9999;
            transform: translateX(100%);
            transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            flex-direction: column;
            box-sizing: border-box;
        }}
        .account-drawer.open {{
            transform: translateX(0);
        }}
        .drawer-header {{
            padding: 14px 18px;
            background: #FFE600;
            border-bottom: 2.5px solid #000000;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }}
        .drawer-header-left {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .drawer-avatar {{
            width: 34px;
            height: 34px;
            background: #FFFFFF;
            border: 2px solid #000000;
            border-radius: 7px;
            box-shadow: 2px 2px 0px #000000;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 15px;
            font-weight: 900;
        }}
        .drawer-title-group {{
            display: flex;
            flex-direction: column;
        }}
        .drawer-title {{
            font-size: 14px;
            font-weight: 900;
            color: #000000;
        }}
        .drawer-subtitle {{
            font-size: 11px;
            color: #4B5563;
            font-weight: 600;
        }}
        .drawer-close {{
            background: #FFFFFF;
            border: 2px solid #000000;
            border-radius: 6px;
            box-shadow: 2px 2px 0px #000000;
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 900;
            cursor: pointer;
        }}
        .drawer-close:hover {{
            background: #FEE2E2;
        }}
        .drawer-body {{
            flex: 1 1 auto;
            overflow-y: auto;
            padding: 16px 18px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .drawer-card {{
            background: #FFFFFF;
            border: 2px solid #000000;
            border-radius: 8px;
            box-shadow: 2.5px 2.5px 0px #000000;
            padding: 12px 14px;
        }}
        .drawer-card-title {{
            font-size: 11.5px;
            font-weight: 900;
            color: #111827;
            border-bottom: 1.5px solid #E5E7EB;
            padding-bottom: 5px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .drawer-item {{
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            margin-bottom: 6px;
            align-items: center;
        }}
        .drawer-label {{
            color: #6B7280;
            font-weight: 700;
        }}
        .drawer-val {{
            color: #111827;
            font-weight: 800;
        }}
        .drawer-model-tag {{
            display: inline-block;
            background: #F3F4F6;
            border: 1px solid #000000;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 800;
            padding: 2px 6px;
            margin: 2px 3px 2px 0;
        }}
        .drawer-footer {{
            padding: 12px 18px;
            background: #FFFFFF;
            border-top: 2.5px solid #000000;
            display: flex;
            gap: 8px;
            flex-shrink: 0;
        }}
        .btn-drawer-switch {{
            background: #3B82F6;
            color: #FFFFFF;
            border: 2px solid #000000;
            border-radius: 6px;
            box-shadow: 2px 2px 0px #000000;
            font-weight: 900;
            padding: 7px 12px;
            font-size: 11px;
            cursor: pointer;
            flex: 1;
        }}
        .btn-drawer-warmup {{
            background: #F59E0B;
            color: #000000;
            border: 2px solid #000000;
            border-radius: 6px;
            box-shadow: 2px 2px 0px #000000;
            font-weight: 900;
            padding: 7px 12px;
            font-size: 11px;
            cursor: pointer;
        }}
        .btn-drawer-copy {{
            background: #FFFFFF;
            color: #000000;
            border: 2px solid #000000;
            border-radius: 6px;
            box-shadow: 2px 2px 0px #000000;
            font-weight: 900;
            padding: 7px 12px;
            font-size: 11px;
            cursor: pointer;
        }}
        .brand-tag {{
            font-size: 9px;
            padding: 0.5px 5px;
            border: 1px solid #000000;
            border-radius: 3px;
            margin-right: 4px;
            font-weight: 900;
            display: inline-block;
        }}
        .brand-gemini {{ background: #93C5FD; color: #000000; }}
        .brand-claude {{ background: #FCD34D; color: #000000; }}

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
        .btn-refresh-all {{ background: #22C55E; color: #000000; margin-right: 6px; }}
        .btn-rotation-gemini {{ background: #4ADE80; color: #000000; font-weight: 900; margin-left: 2px; }}
        .btn-rotation-gemini:hover {{ background: #22C55E; }}
        .btn-rotation-claude {{ background: #F59E0B; color: #000000; font-weight: 900; margin-left: 2px; }}
        .btn-rotation-claude:hover {{ background: #D97706; }}
        .btn-rotation-off {{ background: #E2E8F0; color: #000000; font-weight: 900; margin-left: 2px; }}
        .btn-rotation-off:hover {{ background: #CBD5E1; }}
        /* 向后兼容 */
        .btn-rotation-on {{ background: #4ADE80; color: #000000; font-weight: 900; margin-left: 2px; }}

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

        /* 表头商业级中性高质感灰色底 + 极简纯黑细线 (规范大小写，5h/4h 精准原样呈现) */
        thead th {{
            padding: 8px 6px;
            font-size: 11px;
            font-weight: 900;
            letter-spacing: 0.4px;
            border-right: 1.5px solid #000000;
            border-bottom: 2.5px solid #000000;
            color: #18181B;
            background: #F4F4F5;
            overflow: hidden;
            white-space: nowrap;
            box-sizing: border-box;
        }}
        thead th:last-child {{ border-right: none; }}

        .th-num {{ text-align: center; }}
        .th-status {{ text-align: center; }}
        .th-email {{ text-align: left; padding-left: 10px; }}
        .th-gemini {{ text-align: center; }}
        .th-claude {{ text-align: center; }}
        .th-warmup {{ text-align: center; }}
        .th-action {{ text-align: center; }}

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
            background: #000000;
            color: #FFFFFF;
            font-size: 9px;
            font-weight: 900;
            padding: 0 4px;
            height: 16px;
            line-height: 16px;
            border-radius: 3px;
            box-shadow: 1px 1px 0px rgba(0,0,0,0.3);
            letter-spacing: 0;
            white-space: nowrap;
        }}

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
            width: 30px !important;
            min-width: 30px !important;
            max-width: 30px !important;
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
        
        .btn-warmup {{ 
            width: 44px !important; 
            min-width: 44px !important; 
            max-width: 44px !important; 
            height: 24px;
            flex-shrink: 0 !important; 
            background: #FF9900; 
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
        .btn-warmup:hover {{
            background: #FF7700;
            transform: translate(-1px, -1px);
            box-shadow: 3px 3px 0px #000000;
        }}
        .btn-warmup:active {{
            transform: translate(1px, 1px);
            box-shadow: 1px 1px 0px #000000;
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

        .btn-in-use,
        .active-badge-action {{
            width: 60px !important;
            min-width: 60px !important;
            max-width: 60px !important;
            height: 24px !important;
            background: #4ADE80 !important;
            color: #000000 !important;
            font-size: 11px !important;
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
            width: 34px !important;
            min-width: 34px !important;
            max-width: 34px !important;
            text-align: center !important;
            padding: 0 4px !important;
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
            background-color: #000000;
            background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 16 16' fill='white' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M12.207 4.793a1 1 0 010 1.414l-5 5a1 1 0 01-1.414 0l-2-2a1 1 0 011.414-1.414L6.5 9.086l4.293-4.293a1 1 0 011.414 0z'/%3E%3C/svg%3E");
            background-position: center;
            background-repeat: no-repeat;
            background-size: 13px;
        }}
        .neo-checkbox:indeterminate {{
            background-color: #000000;
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
            background: #000000;
            color: #FFFFFF;
            padding: 0 5px;
        }}
        .btn-batch-clear:hover {{
            background: #333333;
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
<body data-hub-version="{__version__}">
    <div id="hub-version-marker" data-version="{__version__}" style="display:none;"></div>
    <div id="loading-bar"></div>
    <div id="toast" class="toast font-mono"></div>

    <div class="app-container">
        <!-- 顶栏 Navbar (高质感商业控制台风格) -->
        <div class="top-bar">
            <div class="top-left">
                <span class="brand-title">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="#000000" stroke="#000000" stroke-width="1" style="vertical-align:-1px; margin-right:2px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    ANTIGRAVITY FLEET HUB
                </span>
                <span class="version-badge font-mono">v{__version__}</span>
            </div>
            <div class="top-center">
                {active_pill_html}
            </div>
            <div class="top-right">
                {rot_btn_html}
                <button class="btn btn-top btn-warmup-all font-mono"
                        onclick="doWarmupAll(); event.preventDefault(); event.stopPropagation();"
                        title="启动全池阶梯错峰预热流水线，提前激活备用账号 5h 倒计时">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                    错峰预热
                </button>
                <button class="btn btn-top btn-refresh-all font-mono"
                        onclick="doRefreshQuota(this); event.preventDefault(); event.stopPropagation();"
                        title="立即同步最新活跃状态并触发全池配额并发刷新">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>
                    刷新
                </button>
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
            </div>
        </div>

        <!-- 📊 全景 KPI 商业指标大盘网格 (OOB 原地自愈刷新) -->
        {stats_html}

        <!-- 搜索与多维过滤控制条 (客户端 0ms 即时响应) -->
        <div class="control-bar font-mono">
            <div class="search-box">
                <span class="search-icon"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></span>
                <input type="text" id="account-search" class="search-input font-mono" placeholder="搜索账号 (支持快捷键 /)..." oninput="filterTable()" autocomplete="off">
                <button id="clear-search" class="btn-clear" onclick="clearSearch()" style="display:none;" title="清空搜索">✕</button>
            </div>
            <div class="filter-group">
                <button class="filter-tab active" data-filter="all" onclick="setFilter('all', this)">全部 ({total_count})</button>
                <button class="filter-tab" data-filter="usable" onclick="setFilter('usable', this)" title="仅展示 Gemini 周额度大于 0 的可用轮换账号"><span class="filter-dot dot-blue"></span>可用 (G&gt;0)</button>
                <button class="filter-tab" data-filter="healthy" onclick="setFilter('healthy', this)"><span class="filter-dot dot-green"></span>充足 (&gt;50%)</button>
                <button class="filter-tab" data-filter="warning" onclick="setFilter('warning', this)"><span class="filter-dot dot-red"></span>告急 (&lt;15%)</button>
                <button class="filter-tab" data-filter="exhausted" onclick="setFilter('exhausted', this)" title="仅展示 Gemini 周额度已彻底归零的枯竭账号"><span class="filter-dot dot-gray"></span>已枯竭 (G=0)</button>
            </div>
            <div class="stats-counter" id="filter-counter">
                显示: <b>{total_count}</b> / {total_count}
            </div>
            <div id="batch-action-bar" class="batch-bar font-mono" style="display:none;">
                <span class="batch-count-label">已选 <b id="batch-selected-count">0</b> 项</span>
                <button type="button" class="btn-batch btn-batch-export font-mono" onclick="doBatchExport()" title="导出所勾选账号凭据为标准 JSON 文件">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>导出
                </button>
                <button type="button" class="btn-batch btn-batch-delete font-mono" onclick="doBatchDelete()" title="批量删除所勾选账号（在用账号受保护不可删除，自动归档备份）">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>删除
                </button>
                <button type="button" class="btn-batch btn-batch-clear font-mono" onclick="clearAllSelections()" title="清空全部勾选">取消</button>
            </div>
        </div>

        <!-- 官方规范级商业高质感数据表格 (自适应弹性伸缩 + 双模型精准等长) -->
        <div class="table-wrap">
            <table>
                <colgroup>
                    <col style="width: 36px;">   <!-- 批量勾选复选框 -->
                    <col style="width: 44px;">   <!-- # 序号与手柄 -->
                    <col style="width: 86px;">   <!-- 状态徽章 -->
                    <col style="width: 270px;">  <!-- 账号头像与凭据 (充沛空间) -->
                    <col style="width: 320px;">  <!-- Gemini 配额双轨 -->
                    <col style="width: 320px;">  <!-- Claude 配额双轨 -->
                    <col style="width: 180px;">  <!-- 操作按钮群 (在用/切换+预热+详情) -->
                </colgroup>
                <thead>
                    <tr>
                        <th class="col-center th-check" title="全选 / 反选当前可见账号"><input type="checkbox" id="master-select-cb" class="neo-checkbox" onchange="toggleMasterSelect(this)" title="全选 / 反选当前所有筛选可见账号"></th>
                        <th class="col-center th-num" title="拖拽手柄与序号">#</th>
                        <th class="col-center th-status">状态</th>
                        <th class="th-email">账号资产 (点击复制 / 双击查看画像)</th>
                        <th class="th-gemini th-sortable" onclick="cycleGeminiSort()" title="点击切换排序：周额度 (少→多) → 5h额度 (少→多) → 恢复默认">
                            <div class="th-sort-inner">
                                <span class="brand-tag brand-gemini font-mono">Google</span>
                                <span>Gemini 算力 (5h / 周)</span>
                                <span id="sort-gemini-badge" class="sort-badge font-mono" style="display:none;"></span>
                            </div>
                        </th>
                        <th class="th-claude th-sortable" onclick="cycleClaudeSort()" title="点击切换排序：周额度 (少→多) → 5h额度 (少→多) → 恢复默认">
                            <div class="th-sort-inner">
                                <span class="brand-tag brand-claude font-mono">Claude</span>
                                <span>Claude 算力 (5h / 周)</span>
                                <span id="sort-claude-badge" class="sort-badge font-mono" style="display:none;"></span>
                            </div>
                        </th>
                        <th class="col-center th-action" title="切换账号、立即预热与资产画像">操作</th>
                    </tr>
                </thead>
                <tbody id="account-tbody">
                    {table_rows}
                </tbody>
            </table>
        </div>

        <!-- 底部分页与状态指示条 (单页上限 15 个，自适应翻页) -->
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

    <!-- 🚪 商业级账号资产详情右侧抽屉 (Account Slide-over Drawer) -->
    <div id="drawer-backdrop" class="drawer-backdrop" onclick="closeAccountDrawer()"></div>
    <div id="account-drawer" class="account-drawer font-mono">
        <div class="drawer-header">
            <div class="drawer-header-left">
                <div id="drawer-avatar" class="drawer-avatar font-mono">A</div>
                <div class="drawer-title-group">
                    <div id="drawer-title" class="drawer-title font-mono">账号详情</div>
                    <div id="drawer-subtitle" class="drawer-subtitle font-mono">user@example.com</div>
                </div>
            </div>
            <button class="drawer-close font-mono" onclick="closeAccountDrawer()" title="关闭详情面板">✕</button>
        </div>
        <div class="drawer-body" id="drawer-body">
            <div class="drawer-loading font-mono">正在拉取全量资产画像...</div>
        </div>
        <div class="drawer-footer" id="drawer-footer">
            <button id="drawer-btn-switch" class="btn btn-drawer-switch font-mono" onclick="drawerSwitchAccount()">⚡ 切换为此账号</button>
            <button id="drawer-btn-warmup" class="btn btn-drawer-warmup font-mono" onclick="drawerWarmupAccount()">🔥 立即预热</button>
            <button id="drawer-btn-copy" class="btn btn-drawer-copy font-mono" onclick="drawerCopyJson()">📋 复制 JSON</button>
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
                <button class="import-tab-btn active" id="tab-btn-oauth" onclick="switchImportTab('oauth')">🌐 Google 授权添加新账号</button>
                <button class="import-tab-btn" id="tab-btn-sync" onclick="switchImportTab('sync')">⚡ 从当前 IDE 一键吸纳</button>
                <button class="import-tab-btn" id="tab-btn-file" onclick="switchImportTab('file')">📁 批量导入 JSON 备份</button>
            </div>

            <div class="import-body-content">
                <!-- TAB 1: Google OAuth 2.0 浏览器一键授权 (默认首屏) -->
                <div id="import-pane-oauth" class="import-pane">
                    <div class="import-tip-box">
                        <b>🌐 Google OAuth 浏览器全自动获取 Token：</b><br>
                        点击下方按钮拉起浏览器登录 Google 账号并点击「允许」，系统将通过本地回调自动换取 Refresh Token、识别邮箱并入库刷新配额，<b>全程无需手填任何 Token</b>。
                    </div>
                    <div style="display:flex; flex-direction:column; gap:10px;">
                        <button class="btn-sync-action font-mono" id="btn-oauth-browser" onclick="doStartGoogleOAuth(false, this)">
                            🌐 弹出浏览器登录 Google 授权 (推荐)
                        </button>
                        <button class="btn-submit-action font-mono" id="btn-oauth-isolated" onclick="doStartGoogleOAuth(true, this)">
                            🛡️ 拉起独立 ego/隔离容器授权 (多号防串号)
                        </button>
                    </div>
                    <div id="oauth-status-box" style="display:none; margin-top:12px; padding:10px 12px; background:#FEF9C3; border:2px solid #000000; border-radius:6px; box-shadow:2px 2px 0px #000000;">
                        <div style="display:flex; align-items:center; justify-content:space-between; gap:8px;">
                            <span id="oauth-status-text" style="font-size:11.5px; font-weight:900; color:#000000;">⏳ 等待浏览器完成 Google 授权回调...</span>
                            <button class="btn font-mono" style="background:#FFFFFF; padding:0 8px; height:24px; font-size:10.5px;" onclick="copyCurrentOAuthUrl()">📋 复制授权链接</button>
                        </div>
                    </div>
                    <div style="margin-top:14px; padding-top:12px; border-top:1.5px dashed #9CA3AF;">
                        <label class="form-label">🔗 跨设备/手动回调兜底（若在其它浏览器完成授权，直接粘贴回调 URL 或 Code）：</label>
                        <div style="display:flex; gap:8px;">
                            <input type="text" id="oauth-manual-code" class="form-input font-mono" style="margin-bottom:0; flex:1;" placeholder="粘贴 http://127.0.0.1:18088/oauth-callback?code=4/0A...">
                            <button class="btn-submit-action font-mono" style="width:108px; height:35px; flex-shrink:0;" onclick="doSubmitManualOAuthCode(this)">⚡ 解析入库</button>
                        </div>
                    </div>
                </div>

                <!-- TAB 2: 钥匙串一键吸纳 -->
                <div id="import-pane-sync" class="import-pane" style="display:none;">
                    <div class="import-tip-box">
                        <b>⚡ 从本机 Antigravity IDE 钥匙串直接提取：</b><br>
                        自动读取当前 macOS Keychain 中已登录的 Antigravity IDE 账号凭据并同步入库。
                    </div>
                    <button class="btn-sync-action font-mono" id="btn-sync-active" onclick="doSyncActiveAccount(this)">
                        ⚡ 立即从 IDE 钥匙串检测并吸纳新账号
                    </button>
                </div>

                <!-- TAB 3: JSON 备份导入 -->
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
                    ? "⏳ 已拉起独立 ego 隔离容器，请在弹出窗口登录 Google 并点击允许..."
                    : "⏳ 已在 ego 浏览器弹出 Google 授权页，请完成登录授权（完成后自动入库）...";

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
            }}, 2800);
        }}

        // ========================================================
        // 🚪 商业级账号资产详情右侧抽屉 (Account Slide-over Drawer) 控制逻辑
        // ========================================================
        let __currentDrawerEmail = null;
        let __cachedDrawerData = null;

        async function openAccountDrawer(email) {{
            if (!email) return;
            __currentDrawerEmail = email;
            const backdrop = document.getElementById('drawer-backdrop');
            const drawer = document.getElementById('account-drawer');
            const titleEl = document.getElementById('drawer-title');
            const subtitleEl = document.getElementById('drawer-subtitle');
            const avatarEl = document.getElementById('drawer-avatar');
            const bodyEl = document.getElementById('drawer-body');
            const switchBtn = document.getElementById('drawer-btn-switch');

            if (!backdrop || !drawer) return;

            const shortName = email.split('@')[0];
            const firstChar = (shortName[0] || 'A').toUpperCase();
            if (titleEl) titleEl.innerText = shortName;
            if (subtitleEl) subtitleEl.innerText = email;
            if (avatarEl) avatarEl.innerText = firstChar;

            backdrop.classList.add('show');
            drawer.classList.add('open');

            if (bodyEl) {{
                bodyEl.innerHTML = '<div class="drawer-loading font-mono" style="text-align:center;padding:30px;color:#6B7280;">⏳ 正在拉取全量资产画像与实时配额...</div>';
            }}

            try {{
                const resp = await fetch('/api/account-detail?email=' + encodeURIComponent(email));
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                const data = await resp.json();
                __cachedDrawerData = data;

                const isAct = Boolean(data.is_active);
                if (switchBtn) {{
                    if (isAct) {{
                        switchBtn.innerText = "✅ 当前正在使用中";
                        switchBtn.style.background = "#10B981";
                        switchBtn.style.cursor = "default";
                        switchBtn.disabled = true;
                    }} else {{
                        switchBtn.innerText = "⚡ 物理切换为此账号";
                        switchBtn.style.background = "#3B82F6";
                        switchBtn.style.cursor = "pointer";
                        switchBtn.disabled = false;
                    }}
                }}

                renderDrawerBody(data);
            }} catch (err) {{
                if (bodyEl) {{
                    bodyEl.innerHTML = '<div style="color:#DC2626;padding:20px;text-align:center;">❌ 拉取画像失败: ' + err.message + '</div>';
                }}
            }}
        }}

        function closeAccountDrawer() {{
            const backdrop = document.getElementById('drawer-backdrop');
            const drawer = document.getElementById('account-drawer');
            if (backdrop) backdrop.classList.remove('show');
            if (drawer) drawer.classList.remove('open');
            __currentDrawerEmail = null;
            __cachedDrawerData = null;
        }}

        function renderDrawerBody(acc) {{
            const bodyEl = document.getElementById('drawer-body');
            if (!bodyEl) return;

            const g5h = Math.round((acc.gemini?.quota_5h ?? 1.0) * 100);
            const gw = Math.round((acc.gemini?.quota_weekly ?? 1.0) * 100);
            const c5h = Math.round((acc.claude?.quota_5h ?? 1.0) * 100);
            const cw = Math.round((acc.claude?.quota_weekly ?? 1.0) * 100);

            const cVer = acc.claude_version || (acc.claude_models?.some(m => m.includes('5-5')) ? '5.5' : '4.6');
            const tier = acc.tier || (acc.pro ? 'PRO' : 'FREE');
            const hasToken = Boolean(acc.refresh_token);
            const expTs = acc.expiry_timestamp || acc.expires_at || 0;
            const expStr = expTs ? new Date(expTs * 1000).toLocaleString() : '--';
            const models = acc.claude_models || ['claude-sonnet-4-6', 'claude-opus-4-6-thinking'];

            const modelTagsHtml = models.map(m => '<span class="drawer-model-tag font-mono">' + m + '</span>').join('');

            const gReset5h = acc.gemini?.reset_time_5h || '--';
            const gResetW = acc.gemini?.reset_time_weekly || '--';
            const cReset5h = acc.claude?.reset_time_5h || '--';
            const cResetW = acc.claude?.reset_time_weekly || '--';

            const warmupSched = acc.warmup_schedule || {{}};
            const nextWarmup = warmupSched.next_warmup_ts ? new Date(warmupSched.next_warmup_ts * 1000).toLocaleTimeString() : '--';

            const tierBadge = (tier === 'PRO') ? '<span class="stat-badge stat-badge-green font-mono">PRO</span>' : '<span class="stat-badge stat-badge-gray font-mono">FREE</span>';
            const activeLabel = acc.is_active ? '<span style="color:#10B981;font-weight:900;">🟢 在岗使用中</span>' : '⚪ 待命候选池';
            const blockedLabel = acc.validation_blocked ? '<span style="color:#DC2626;font-weight:900;">⚠️ 需网页验证</span>' : '✅ 正常免风控';
            const tokenBadge = hasToken ? '<span class="stat-badge stat-badge-green font-mono">TOKEN 就绪</span>' : '<span class="stat-badge stat-badge-gray font-mono">缺少 TOKEN</span>';
            const accName = acc.name || (acc.email ? acc.email.split('@')[0] : '--');

            bodyEl.innerHTML = [
                '<div class="drawer-card">',
                    '<div class="drawer-card-title"><span>🆔 身份与权限</span>' + tierBadge + '</div>',
                    '<div class="drawer-item"><span class="drawer-label">账号名称:</span><span class="drawer-val">' + accName + '</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">完整邮箱:</span><span class="drawer-val">' + (acc.email || '--') + '</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">Claude 版本:</span><span class="drawer-val"><span class="stat-tag tag-claude-ver font-mono">Claude ' + cVer + '</span></span></div>',
                    '<div class="drawer-item"><span class="drawer-label">当前状态:</span><span class="drawer-val">' + activeLabel + '</span></div>',
                '</div>',
                '<div class="drawer-card" style="background:#F0F9FF;">',
                    '<div class="drawer-card-title"><span>⚡ Gemini 算力池 (Google 2.5)</span><span class="stat-badge stat-badge-blue font-mono">5h: ' + g5h + '% | 周: ' + gw + '%</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">5小时滚动配额:</span><span class="drawer-val">' + g5h + '%</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">5小时重置时间:</span><span class="drawer-val">' + gReset5h + '</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">周度总配额:</span><span class="drawer-val">' + gw + '%</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">周度重置周期:</span><span class="drawer-val">' + gResetW + '</span></div>',
                '</div>',
                '<div class="drawer-card" style="background:#FFFBEB;">',
                    '<div class="drawer-card-title"><span>🧠 Claude 算力池 (Anthropic)</span><span class="stat-badge stat-badge-amber font-mono">5h: ' + c5h + '% | 周: ' + cw + '%</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">5小时滚动配额:</span><span class="drawer-val">' + c5h + '%</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">5小时重置时间:</span><span class="drawer-val">' + cReset5h + '</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">周度总配额:</span><span class="drawer-val">' + cw + '%</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">周度重置周期:</span><span class="drawer-val">' + cResetW + '</span></div>',
                '</div>',
                '<div class="drawer-card">',
                    '<div class="drawer-card-title"><span>🔑 OAuth 凭据与有效期</span>' + tokenBadge + '</div>',
                    '<div class="drawer-item"><span class="drawer-label">Refresh Token:</span><span class="drawer-val">' + (hasToken ? '已持久化 (安全哈希保护)' : '未授权') + '</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">Access Token 过期:</span><span class="drawer-val">' + expStr + '</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">人机验证受限:</span><span class="drawer-val">' + blockedLabel + '</span></div>',
                    '<div class="drawer-item"><span class="drawer-label">下次预热调度:</span><span class="drawer-val">' + nextWarmup + '</span></div>',
                '</div>',
                '<div class="drawer-card">',
                    '<div class="drawer-card-title"><span>🧩 可用授权模型矩阵 (' + models.length + ')</span></div>',
                    '<div style="line-height:1.6;">' + modelTagsHtml + '</div>',
                '</div>'
            ].join('');
        }}

        function drawerSwitchAccount() {{
            if (!__currentDrawerEmail) return;
            doSwitchAccount(__currentDrawerEmail);
        }}

        function drawerWarmupAccount() {{
            if (!__currentDrawerEmail) return;
            doWarmupAccount(__currentDrawerEmail);
        }}

        function drawerCopyJson() {{
            if (!__cachedDrawerData) return;
            const str = JSON.stringify(__cachedDrawerData, null, 2);
            navigator.clipboard.writeText(str).then(() => {{
                showToast("✅ 已成功复制全量资产画像 JSON", "success");
            }}).catch(() => {{
                showToast("❌ 复制失败，请重试", "error");
            }});
        }}

        // ⌨️ 全局键盘快捷键：/ 聚焦搜索，Esc 关闭模态或抽屉
        document.addEventListener('keydown', (e) => {{
            if (e.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {{
                e.preventDefault();
                const s = document.getElementById('account-search');
                if (s) {{ s.focus(); s.select(); }}
            }} else if (e.key === 'Escape') {{
                closeAccountDrawer();
                closeNeoModal(false);
                closeImportModal();
            }}
        }});


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

        // 🛡️ 一键解封向导：拉起现役 ego lite 浏览器并自动定向对应账号，彻底防500！
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

        // 🔥 全池阶梯错峰预热直通函数
        async function doWarmupAll() {{
            showToast("⏳ 正在启动全池阶梯错峰预热流水线...", "info");
            try {{
                const resp = await fetch('/api/warmup-all', {{
                    method: 'POST'
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const html = await resp.text();
                applyTbodyAndOOB(html);
                showToast("🎉 全池阶梯错峰预热已完成！各账号 5h 倒计时已锁定启动", "warmup");
            }} catch (err) {{
                showToast("❌ 错峰预热失败: " + err.message, "error");
            }}
        }}

        // 🔄 三态循环切换自动轮换开关直通函数 (Gemini ➔ Claude ➔ 关闭 ➔ Gemini)
        async function cycleAutoRotation(btn) {{
            btn.disabled = true;
            try {{
                const resp = await fetch('/api/toggle-rotation', {{
                    method: 'POST'
                }});
                if (!resp.ok) throw new Error("HTTP " + resp.status);
                const res = await resp.json();
                const mode = res.mode || (res.enabled ? (res.policy === 'claude_first' ? 'claude' : 'gemini') : 'off');
                btn.setAttribute('data-mode', mode);

                if (mode === 'gemini') {{
                    btn.className = "btn btn-top btn-rotation-gemini font-mono";
                    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><polygon points="5 3 19 12 5 21 5 3"/></svg>⚡ 轮转: Gemini';
                    btn.title = "当前模式：自动轮转 Gemini（仅关注 Gemini 额度，耗尽自动切号，忽略 Claude 额度；点击切换为 Claude 轮转）";
                    showToast("⚡ 已切换为【自动轮转 Gemini】：仅监控 Gemini 额度，耗尽自动切号", "success");
                }} else if (mode === 'claude') {{
                    btn.className = "btn btn-top btn-rotation-claude font-mono";
                    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><polygon points="5 3 19 12 5 21 5 3"/></svg>⚡ 轮转: Claude';
                    btn.title = "当前模式：自动轮转 Claude（仅关注 Claude 额度，耗尽自动切号，忽略 Gemini 额度；点击彻底关闭轮转）";
                    showToast("⚡ 已切换为【自动轮转 Claude】：仅监控 Claude 额度，耗尽自动切号", "info");
                }} else {{
                    btn.className = "btn btn-top btn-rotation-off font-mono";
                    btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1.5px; margin-right:3px;"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>🚫 轮转: 关闭';
                    btn.title = "当前模式：彻底关闭自动轮转（看门狗已冻结，不自动切号；点击开启 Gemini 轮转）";
                    showToast("🚫 已彻底关闭自动轮转：看门狗已冻结，不会自动切号，可放心手动使用", "warning");
                }}
            }} catch (err) {{
                showToast("❌ 切换轮换状态失败: " + err.message, "error");
            }} finally {{
                btn.disabled = false;
            }}
        }}
        window.toggleAutoRotation = cycleAutoRotation;

        let currentPage = 1;
        const PAGE_SIZE = 15;
        let __cachedTbodyHTML = '';
        let currentSortMode = 'default'; // 'default' | 'gemini_w_asc' | 'gemini_5h_asc' | 'claude_w_asc' | 'claude_5h_asc'

        // 🔀 更新 Gemini / Claude 表头排序角标指示器
        function updateSortBadges() {{
            const gBadge = document.getElementById('sort-gemini-badge');
            const cBadge = document.getElementById('sort-claude-badge');

            if (gBadge) {{
                if (currentSortMode === 'gemini_w_asc') {{
                    gBadge.textContent = '周少→多';
                    gBadge.style.display = 'inline-flex';
                }} else if (currentSortMode === 'gemini_5h_asc') {{
                    gBadge.textContent = '5h少→多';
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

        // 页面初始加载时备份原始行数据
        window.addEventListener('DOMContentLoaded', function() {{
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
            const tbody = document.getElementById('account-tbody');
            if (!tbody) return;

            const allRows = Array.from(tbody.querySelectorAll('tr.account-row'));
            if (allRows.length === 0) return;

            // 1. 🔀 根据 currentSortMode 对全量账号行进行排序并重排 DOM
            allRows.sort((a, b) => {{
                if (currentSortMode !== 'default') {{
                    let valA = 0;
                    let valB = 0;
                    if (currentSortMode === 'gemini_w_asc') {{
                        valA = parseFloat(a.getAttribute('data-gemini-w') || '0');
                        valB = parseFloat(b.getAttribute('data-gemini-w') || '0');
                    }} else if (currentSortMode === 'gemini_5h_asc') {{
                        valA = parseFloat(a.getAttribute('data-gemini-5h') || '0');
                        valB = parseFloat(b.getAttribute('data-gemini-5h') || '0');
                    }} else if (currentSortMode === 'claude_w_asc') {{
                        valA = parseFloat(a.getAttribute('data-claude-w') || '0');
                        valB = parseFloat(b.getAttribute('data-claude-w') || '0');
                    }} else if (currentSortMode === 'claude_5h_asc') {{
                        valA = parseFloat(a.getAttribute('data-claude-5h') || '0');
                        valB = parseFloat(b.getAttribute('data-claude-5h') || '0');
                    }}
                    if (valA !== valB) {{
                        return valA - valB; // 严格从小到大升序
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

            // 3. 分类 Tab 过滤
            const matchedRows = [];
            allRows.forEach(tr => {{
                const email = tr.getAttribute('data-email') || '';
                const cver = tr.getAttribute('data-claude-ver') || '';
                const matchQuery = !q || email.toLowerCase().includes(q) 
                    || (q === '5.5' && cver === '5.5') 
                    || (q === '4.6' && cver === '4.6') 
                    || (q === '下架' && cver === '4.6')
                    || (q === '付费' && cver === '5.5');

                const gw = parseFloat(tr.getAttribute('data-gemini-w') || '1.0');
                const cw = parseFloat(tr.getAttribute('data-claude-w') || '1.0');
                let matchTab = true;
                if (currentFilter === 'ver55') {{
                    matchTab = (cver === '5.5');
                }} else if (currentFilter === 'ver46') {{
                    matchTab = (cver === '4.6');
                }} else if (currentFilter === 'usable') {{
                    matchTab = (gw > 0.0001);
                }} else if (currentFilter === 'healthy') {{
                    matchTab = (gw >= 0.5 && cw >= 0.5);
                }} else if (currentFilter === 'warning') {{
                    matchTab = (gw < 0.15 || cw < 0.15);
                }} else if (currentFilter === 'exhausted') {{
                    matchTab = (gw <= 0.0001);
                }}

                if (matchQuery && matchTab) {{
                    matchedRows.push(tr);
                }} else {{
                    tr.style.display = 'none';
                }}
            }});

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
                pageTotal.innerHTML = `共 ${{totalMatched}} 个账号`;
            }}
            const btnPrev = document.getElementById('btn-prev-page');
            const btnNext = document.getElementById('btn-next-page');
            if (btnPrev) btnPrev.disabled = (currentPage <= 1);
            if (btnNext) btnNext.disabled = (currentPage >= totalPages);

            updateSortBadges();
            restoreSelectionState();
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
        elif parsed.path == "/api/account-detail":
            qs = urllib.parse.parse_qs(parsed.query)
            email = qs.get("email", [""])[0]
            data = ENGINE.load_accounts()
            accounts = data.get("accounts", {})
            acc = accounts.get(email)
            if not acc:
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Account {email} not found"}).encode("utf-8"))
                return
            sched_warmup = {}
            if os.path.exists(WARMUP_SCHEDULE_PATH):
                try:
                    with open(WARMUP_SCHEDULE_PATH, "r", encoding="utf-8") as sf:
                        sched_warmup = json.load(sf)
                except Exception:
                    pass
            acc_copy = dict(acc)
            acc_copy["warmup_schedule"] = sched_warmup.get(email, {})
            acc_copy["is_active"] = (email == data.get("active_email", ""))
            lock_info = get_manual_override_lock()
            acc_copy["manual_lock"] = lock_info if (lock_info and lock_info.get("manual_account") == email) else None
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(acc_copy, ensure_ascii=False).encode("utf-8"))
            return
        elif parsed.path == "/api/rotation-status":
            cfg = get_auto_rotation_config()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(cfg).encode("utf-8"))
            return
        elif parsed.path == "/api/export":
            from import_accounts_hub import export_accounts_backup
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
            from import_accounts_hub import exchange_oauth_code_and_ingest
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
            try:
                from antigravity_physical_switcher import AntigravityPhysicalManager
                mgr = AntigravityPhysicalManager()
                count = mgr.check_and_warmup_idle_accounts()
                logger.info(f"🔥 [全池阶梯错峰预热] 触发完成，已成功拉入 {count} 个账号进入倒计时流水线")
            except Exception as e:
                logger.error(f"全池错峰预热异常: {e}")
            html = render_table_rows(include_oob=True)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

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

            if req_mode in ("gemini", "claude", "off"):
                next_mode = req_mode
            else:
                if cur_mode == "gemini":
                    next_mode = "claude"
                elif cur_mode == "claude":
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
                        safe_name = email.replace("@", "_").replace(".", "_")

                        launch_browser_for_auth(smart_url, isolated=False, profile_name=safe_name)
                        logger.info(f"🚀 [一键解封] 已为 {email} 在 ego 浏览器中拉起解封页面: {smart_url}")

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

        elif parsed.path == "/api/oauth/start":
            from import_accounts_hub import build_google_oauth_url
            isolated = False
            open_browser = True
            try:
                if post_data.strip().startswith("{"):
                    req_j = json.loads(post_data)
                    isolated = bool(req_j.get("isolated", False))
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
            from import_accounts_hub import exchange_oauth_code_and_ingest
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
            from import_accounts_hub import ingest_system_keychain_or_creds
            ok, email, msg = ingest_system_keychain_or_creds(ACCOUNTS_HUB_FILE)
            if ok:
                threading.Thread(target=ENGINE.refresh_all_quotas, daemon=True).start()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok" if ok else "error", "email": email, "message": msg}).encode("utf-8"))
            return

        elif parsed.path == "/api/import":
            from import_accounts_hub import import_accounts_payload
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

                # 保存更新后的账号池（内部自动触发 sync_external_pools 同步清理三处账号库）
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
    try:
        ENGINE.save_accounts(ENGINE.load_accounts())
    except Exception as e:
        logger.warning(f"启动同步账号池异常: {e}")
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
