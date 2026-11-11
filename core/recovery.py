#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/recovery.py - Antigravity 多会话精准嗅探与零 UI 侵入断点接力中枢
=====================================================================
核心契约：
1. 100% 官方原生 IPC：调用 language_server agentapi send-message 原生注入提示词；
2. 跨平台兼容 (Linux / macOS)：自动探测 language_server 二进制路径与端口/CSRF Token；
3. 根会话强类型审查：通过 agentapi get-conversation-metadata 过滤子代理 (仅唤醒 nestingDepth==0 根会话)；
4. Teamwork 多智能体断点接力提示词引擎：自动提取在途子代理角色并强令恢复协同管线；
5. 轮换前瞬间快照 (pre_switch_snapshot) 与换号就绪后批量唤醒 (batch_recover_all_working_sessions)。
"""

import os
import sys
import time
import json
import glob
import re
import uuid
import logging
import shutil
import datetime
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

logger = logging.getLogger("SessionRecovery")

DEFAULT_BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")
DEFAULT_SNAPSHOT_PATH = os.path.expanduser("~/.antigravity_hub/data/pre_switch_snapshot.json")

# 探测官方原生二进制路径
CANDIDATE_LS_PATHS = [
    "/opt/Antigravity/resources/bin/language_server",
    "/Applications/Antigravity.app/Contents/Resources/bin/language_server",
    os.path.expanduser("~/.gemini/antigravity/bin/language_server"),
]
LANGUAGE_SERVER_BIN = None
for p in CANDIDATE_LS_PATHS:
    if os.path.isfile(p) and os.access(p, os.X_OK):
        LANGUAGE_SERVER_BIN = p
        break
if not LANGUAGE_SERVER_BIN:
    which_ls = shutil.which("language_server")
    if which_ls:
        LANGUAGE_SERVER_BIN = which_ls


class AntigravitySessionRecoveryManager:
    """会话嗅探与断点接力管理器"""

    def __init__(self, brain_dir: str = DEFAULT_BRAIN_DIR, snapshot_path: str = DEFAULT_SNAPSHOT_PATH):
        self.brain_dir = brain_dir
        self.snapshot_path = snapshot_path
        self._session_meta_cache: Dict[str, bool] = {}
        self._live_ls_env: Dict[str, str] = {}

    def detect_live_ls_env(self) -> Dict[str, str]:
        """
        动态嗅探运行中的 language_server 进程，提取监听端口与 CSRF Token。
        支持从 ~/.gemini/antigravity/daemon/*.json 极速读取，并回退 ps aux + ss / lsof。
        """
        env = {}
        # 1. 优先读取 ~/.gemini/antigravity/daemon/*.json
        daemon_dir = os.path.expanduser("~/.gemini/antigravity/daemon")
        if os.path.isdir(daemon_dir):
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
                    csrf = d_info.get("csrfToken")
                    if pid and http_port and csrf:
                        try:
                            os.kill(int(pid), 0)
                            env["ANTIGRAVITY_LS_ADDRESS"] = f"127.0.0.1:{http_port}"
                            env["ANTIGRAVITY_CSRF_TOKEN"] = str(csrf)
                            env["ANTIGRAVITY_LS_PID"] = str(pid)
                            self._live_ls_env = env
                            return env
                        except OSError:
                            continue
                except Exception:
                    continue

        # 2. 回退机制：通过 ps aux 查找
        try:
            ps_out = subprocess.check_output(["ps", "aux"], text=True)
            ls_pid = None
            csrf = None
            for line in ps_out.splitlines():
                if "language_server" in line and "--csrf_token" in line:
                    parts = line.split()
                    ls_pid = parts[1]
                    m = re.search(r"--csrf_token\s+([a-f0-9-]+)", line)
                    if m:
                        csrf = m.group(1)
                    break

            if not ls_pid or not csrf:
                return env

            ports = []
            # Linux ss 探测
            if sys.platform.startswith("linux") and shutil.which("ss"):
                try:
                    ss_out = subprocess.check_output(["ss", "-tlpn"], text=True)
                    for l in ss_out.splitlines():
                        if f"pid={ls_pid}," in l or f"pid={ls_pid})" in l:
                            m = re.search(r"127\.0\.0\.1:(\d+)", l)
                            if m:
                                ports.append(m.group(1))
                except Exception:
                    pass

            # 回退 lsof 探测
            if not ports and shutil.which("lsof"):
                try:
                    lsof_out = subprocess.check_output(
                        ["lsof", "-nP", "-a", "-iTCP", "-sTCP:LISTEN", "-p", ls_pid],
                        text=True
                    )
                    for l in lsof_out.splitlines():
                        m = re.search(r":(\d+)\s+\(LISTEN\)", l)
                        if m:
                            ports.append(m.group(1))
                except Exception:
                    pass

            for p in sorted(ports, reverse=True):
                env["ANTIGRAVITY_LS_ADDRESS"] = f"127.0.0.1:{p}"
                env["ANTIGRAVITY_CSRF_TOKEN"] = csrf
                env["ANTIGRAVITY_LS_PID"] = ls_pid
                self._live_ls_env = env
                return env

        except Exception as e:
            logger.debug(f"嗅探 language_server 异常: {e}")

        return env

    def get_execution_env(self) -> Dict[str, str]:
        """合并当前环境变量与动态嗅探的 LS 地址与 Token"""
        base_env = os.environ.copy()
        live_env = self.detect_live_ls_env()
        base_env.update(live_env)
        return base_env

    @staticmethod
    def _parse_iso_timestamp(iso_str: str) -> float:
        """兼容解析带纳秒小数与 Z 时区的 RFC3339 时间戳为 Unix epoch 秒"""
        if not iso_str:
            return 0.0
        s = str(iso_str).strip()
        if not s:
            return 0.0
        try:
            # 截断超过 6 位的小数秒以兼容全版本 Python datetime.fromisoformat
            m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", s)
            if m:
                base, frac, tz = m.groups()
                if frac and len(frac) > 7:
                    frac = frac[:7]
                if not tz or tz == "Z":
                    tz = "+00:00"
                elif len(tz) == 5 and tz[0] in "+-":
                    tz = tz[:3] + ":" + tz[3:]
                normalized = f"{base}{frac or ''}{tz}"
                return datetime.datetime.fromisoformat(normalized).timestamp()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            return datetime.datetime.fromisoformat(s).timestamp()
        except Exception:
            return 0.0

    def query_live_cascade_trajectories(self, timeout_sec: float = 10.0) -> Dict[str, Any]:
        """
        【权威运行时真源查询】直连运行中的 Antigravity language_server，调用原生 RPC
        GetAllCascadeTrajectories 获取全部会话当前真实运行状态：
        - status: CASCADE_RUN_STATUS_RUNNING vs CASCADE_RUN_STATUS_IDLE
        - latestExecutorTerminationReason: NO_TOOL_CALL / USER_CANCELED / ERROR / TERMINAL_CUSTOM_HOOK
        - trajectoryMetadata: nestingDepth / parentConversationId / rootConversationId / subagentSpec
        """
        daemon_dir = os.path.expanduser("~/.gemini/antigravity/daemon")
        candidates = []
        if os.path.isdir(daemon_dir):
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
                    csrf = d_info.get("csrfToken")
                    if pid and http_port and csrf:
                        try:
                            os.kill(int(pid), 0)
                            candidates.append((f"127.0.0.1:{http_port}", str(csrf)))
                        except OSError:
                            continue
                except Exception:
                    continue

        if not candidates:
            live_env = self.detect_live_ls_env()
            addr = live_env.get("ANTIGRAVITY_LS_ADDRESS")
            csrf = live_env.get("ANTIGRAVITY_CSRF_TOKEN")
            if addr and csrf:
                candidates.append((addr, csrf))

        for addr, csrf in candidates:
            url = f"http://{addr}/exa.language_server_pb.LanguageServerService/GetAllCascadeTrajectories"
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "x-codeium-csrf-token": csrf,
                },
                method="POST",
            )
            try:
                no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with no_proxy_opener.open(req, timeout=timeout_sec) as resp:
                    payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
                tsum = payload.get("trajectorySummaries")
                if isinstance(tsum, dict) and tsum:
                    return tsum
            except Exception as ex:
                logger.warning(f"查询 GetAllCascadeTrajectories ({addr}) 失败: {ex}")
                continue
        return {}

    def _analyze_transcript_tail(self, lines: List[str]) -> Dict[str, Any]:
        """
        精准分析会话 transcript 尾部结构，判断最近一次对话轮次是否已正常结束。
        """
        last_major_type = ""
        last_major_content = ""
        last_major_tool_calls: List[Any] = []
        last_major_status = ""
        has_error_after_last_major = False

        for tl in reversed(lines[-80:]):
            try:
                td = json.loads(tl)
            except Exception:
                continue
            ttype = td.get("type", "")
            tstatus = str(td.get("status", ""))
            if ttype == "ERROR_MESSAGE" or tstatus == "ERROR":
                has_error_after_last_major = True
                continue
            if ttype in ("EPHEMERAL_MESSAGE", "GENERIC", "CHECKPOINT", "SYSTEM_MESSAGE"):
                continue
            if ttype in ("PLANNER_RESPONSE", "USER_INPUT"):
                last_major_type = ttype
                last_major_content = str(td.get("content", ""))
                last_major_tool_calls = td.get("tool_calls") or []
                last_major_status = tstatus
                break

        cleanly_finished = (
            last_major_type == "PLANNER_RESPONSE"
            and len(last_major_tool_calls) == 0
            and last_major_status == "DONE"
            and not has_error_after_last_major
        )
        return {
            "last_major_type": last_major_type,
            "last_major_content": last_major_content,
            "last_major_tool_calls": last_major_tool_calls,
            "last_major_status": last_major_status,
            "has_error_after_last_major": has_error_after_last_major,
            "cleanly_finished": cleanly_finished,
        }

    def is_root_user_session(self, session_id: str) -> bool:
        """
        通过官方原生 agentapi get-conversation-metadata 进行强类型审查：
        根会话必须满足: nestingDepth == 0 且 parentConversationId == "" 且 subagentSpec 为 null。
        若发现任何父会话指针、嵌套深度大于0或子代理规格，100% 判定为子代理，坚决不向子代理投递接力提示词！
        """
        if session_id in self._session_meta_cache:
            return self._session_meta_cache[session_id]

        if not LANGUAGE_SERVER_BIN:
            return True

        cmd = [LANGUAGE_SERVER_BIN, "agentapi", "get-conversation-metadata", session_id]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, env=self.get_execution_env(), timeout=3)
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                meta = data.get("response", {}).get("conversationMetadata", {}).get("metadata", {})
                parent_id = meta.get("parentConversationId", "")
                nesting_depth = meta.get("nestingDepth", 0)
                subagent_spec = meta.get("subagentSpec")
                if parent_id or nesting_depth > 0 or (subagent_spec is not None):
                    self._session_meta_cache[session_id] = False
                    return False
                self._session_meta_cache[session_id] = True
                return True
        except Exception:
            pass

        return True

    def get_subagent_tree_mtime(self, sub_id: str, visited: Optional[set] = None) -> float:
        """递归获取子代理及其所有后代子代理（Orchestrator、Worker 等）的最大最新活跃时间"""
        if visited is None:
            visited = set()
        if sub_id in visited:
            return 0.0
        visited.add(sub_id)

        sub_dir = os.path.join(self.brain_dir, sub_id)
        if not os.path.isdir(sub_dir):
            return 0.0

        sub_tpath = os.path.join(sub_dir, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.isfile(sub_tpath):
            sub_tpath = os.path.join(sub_dir, "transcript.jsonl")

        max_m = os.path.getmtime(sub_tpath) if os.path.isfile(sub_tpath) else 0.0

        child_sub_dir = os.path.join(sub_dir, ".system_generated", "subagents")
        if os.path.isdir(child_sub_dir):
            for fname in os.listdir(child_sub_dir):
                if fname.endswith(".json"):
                    cid = fname[:-5]
                    cm = self.get_subagent_tree_mtime(cid, visited)
                    if cm > max_m:
                        max_m = cm

        return max_m

    def get_effective_session_mtime(self, session_dir: str, root_mtime: float) -> float:
        """向上穿透统计主会话及其所有在途子代理树的最新活跃时间"""
        eff_mtime = root_mtime
        sub_dir = os.path.join(session_dir, ".system_generated", "subagents")
        if os.path.isdir(sub_dir):
            for fname in os.listdir(sub_dir):
                if fname.endswith(".json"):
                    sub_id = fname[:-5]
                    sm = self.get_subagent_tree_mtime(sub_id)
                    if sm > eff_mtime:
                        eff_mtime = sm
        return eff_mtime

    def check_subagent_is_active(
        self,
        sub_session_id: str,
        max_idle: int = 300,
        parent_session_dir: str = "",
        live_trajectories: Optional[Dict[str, Any]] = None,
        parent_last_planner_mtime: float = 0.0
    ) -> bool:
        """
        检查单个子代理会话是否真正处于运行中：
        - 彻底废除仅因 .json 残留 SUBAGENT_STATE_ALIVE 就永久误判存活的历史 Bug；
        - 若存在权威 LS 运行时状态，严格以 CASCADE_RUN_STATUS_RUNNING 为唯一判据；
        - 回退模式要求：未被 KILLED、近期有写入且其自身 transcript 尾部未正常收尾。
        """
        if parent_session_dir:
            meta_p = os.path.join(parent_session_dir, ".system_generated", "subagents", f"{sub_session_id}.json")
            if os.path.isfile(meta_p):
                try:
                    with open(meta_p, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    if meta.get("state") == "SUBAGENT_STATE_KILLED":
                        return False
                except Exception:
                    pass

        if live_trajectories is not None and sub_session_id in live_trajectories:
            sub_traj = live_trajectories.get(sub_session_id) or {}
            return sub_traj.get("status") == "CASCADE_RUN_STATUS_RUNNING"

        sub_dir = os.path.join(self.brain_dir, sub_session_id)
        if not os.path.isdir(sub_dir):
            return False

        tree_mtime = self.get_subagent_tree_mtime(sub_session_id)
        if tree_mtime <= 0.0:
            return False

        now = time.time()
        effective_cap = min(max_idle, 300)
        if (now - tree_mtime) > effective_cap:
            return False

        sub_tpath = os.path.join(sub_dir, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.isfile(sub_tpath):
            sub_tpath = os.path.join(sub_dir, "transcript.jsonl")
        if not os.path.isfile(sub_tpath):
            return False

        try:
            with open(sub_tpath, "r", encoding="utf-8") as f:
                sub_lines = [l.strip() for l in f if l.strip()]
            if not sub_lines:
                return False
            sub_tail = self._analyze_transcript_tail(sub_lines)
            if sub_tail["cleanly_finished"]:
                return False
        except Exception:
            return False

        return True

    def get_open_conversation_panes(self) -> set:
        """提取当前在 Antigravity 界面中打开的所有活体窗格会话 ID (穿透 aux-pane-v2-session)"""
        open_ids = set()
        app_storage_path = os.path.expanduser("~/.config/Antigravity/app_storage.json")
        if os.path.isfile(app_storage_path):
            try:
                with open(app_storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                v2 = data.get("aux-pane-v2-session", {})
                if isinstance(v2, str):
                    try:
                        v2 = json.loads(v2)
                    except Exception:
                        v2 = {}
                panes = v2.get("conversationPanes", {})
                for cid in panes.keys():
                    if cid and len(cid) >= 32:
                        open_ids.add(cid)
            except Exception as ex:
                logger.debug(f"读取活体窗格异常: {ex}")
        return open_ids

    def get_active_subagents_for_session(
        self,
        session_dir: str,
        max_idle: int = 300,
        live_trajectories: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """探测主会话下属真正在运行的 Subagents ID 列表（严禁把已完成残留 SUBAGENT_STATE_ALIVE 当存活）"""
        active_subs = []
        sub_dir = os.path.join(session_dir, ".system_generated", "subagents")
        if not os.path.isdir(sub_dir):
            return active_subs

        for fname in os.listdir(sub_dir):
            if fname.endswith(".json"):
                sub_id = fname[:-5]
                meta_p = os.path.join(sub_dir, fname)
                try:
                    with open(meta_p, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    if meta.get("state") == "SUBAGENT_STATE_KILLED":
                        continue
                except Exception:
                    pass

                if self.check_subagent_is_active(
                    sub_id,
                    max_idle=max_idle,
                    parent_session_dir=session_dir,
                    live_trajectories=live_trajectories,
                ):
                    active_subs.append(sub_id)

        return active_subs

    def is_session_waiting_for_recovery(self, transcript_path: str) -> bool:
        """
        检查会话尾部是否已经堆叠了一条尚未得到模型响应的【配额已就绪】提示词。
        仅当该提示词已在尾部等待且尚未触发 PLANNER_RESPONSE 时才跳过，杜绝重复堆积；
        一旦模型对上一次接力生成了回复，若后续再次切号，必须允许下一次接力正常注入！
        """
        if not os.path.isfile(transcript_path):
            return False
        try:
            with open(transcript_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            for l in reversed(lines[-25:]):
                d = json.loads(l)
                ttype = d.get("type", "")
                if ttype in ("EPHEMERAL_MESSAGE", "GENERIC", "ERROR_MESSAGE", "CHECKPOINT"):
                    continue
                if ttype in ("USER_INPUT", "SYSTEM_MESSAGE"):
                    content = str(d.get("content", ""))
                    if "【配额已就绪】" in content or "配额已就绪" in content:
                        return True
                    return False
                elif ttype == "PLANNER_RESPONSE":
                    return False
        except Exception:
            pass
        return False

    def scan_active_sessions(
        self,
        max_idle_seconds: int = 300,
        error_grace_seconds: int = 180,
        live_trajectories: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        精准识别需要断点续传唤醒的活跃根会话：
        1. 主路径（Antigravity LS 在线，GetAllCascadeTrajectories 可用）：
           - 仅唤醒 status == CASCADE_RUN_STATUS_RUNNING 的根会话，或拥有在途 RUNNING 后代的根会话；
           - 以及最近 <=180s 内因 EXECUTOR_TERMINATION_REASON_ERROR 意外中断的在途根会话；
           - 彻底跳过 IDLE + NO_TOOL_CALL（已完成）、IDLE + USER_CANCELED（已取消），绝不因窗格保持打开或历史 SUBAGENT_STATE_ALIVE 残留而误唤醒！
        2. 回退路径（LS 不可达）：
           - 收缩回退窗口至 <=300s，彻底取消 open_panes 豁免；
           - 若尾部为正常结束的纯文本 PLANNER_RESPONSE(tc=[], DONE) 且无未完工子代理，坚决跳过。
        """
        if not os.path.exists(self.brain_dir):
            return []

        if live_trajectories is None:
            live_trajectories = self.query_live_cascade_trajectories()

        has_live_ls = bool(live_trajectories)
        running_roots = set()
        if has_live_ls:
            for cid, csum in live_trajectories.items():
                if not isinstance(csum, dict):
                    continue
                if csum.get("status") == "CASCADE_RUN_STATUS_RUNNING":
                    running_roots.add(cid)
                    cmeta = csum.get("trajectoryMetadata") or {}
                    rcid = cmeta.get("rootConversationId")
                    if rcid:
                        running_roots.add(rcid)
                    cur = cmeta.get("parentConversationId")
                    visited_anc = set()
                    while cur and cur not in visited_anc and len(visited_anc) < 16:
                        visited_anc.add(cur)
                        running_roots.add(cur)
                        p_sum = live_trajectories.get(cur) or {}
                        p_meta = p_sum.get("trajectoryMetadata") or {}
                        p_rcid = p_meta.get("rootConversationId")
                        if p_rcid:
                            running_roots.add(p_rcid)
                        cur = p_meta.get("parentConversationId")

        active_sessions = []
        now = time.time()
        fallback_cap = min(max_idle_seconds, 300)
        running_cap = max(max_idle_seconds, 2700)

        for session_id in os.listdir(self.brain_dir):
            sess_path = os.path.join(self.brain_dir, session_id)
            if not os.path.isdir(sess_path) or session_id.startswith(".") or session_id == "tempmediaStorage":
                continue

            transcript_path = os.path.join(sess_path, ".system_generated", "logs", "transcript.jsonl")
            if not os.path.exists(transcript_path):
                transcript_path = os.path.join(sess_path, "transcript.jsonl")

            if not os.path.exists(transcript_path):
                continue

            try:
                root_mtime = os.path.getmtime(transcript_path)
                eff_mtime = self.get_effective_session_mtime(sess_path, root_mtime)

                with open(transcript_path, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f if l.strip()]
                if len(lines) < 3:
                    continue

                tail_info = self._analyze_transcript_tail(lines)

                if has_live_ls:
                    traj = live_trajectories.get(session_id)
                    if not isinstance(traj, dict):
                        continue

                    tmeta = traj.get("trajectoryMetadata") or {}
                    if tmeta.get("parentConversationId") or int(tmeta.get("nestingDepth") or 0) > 0 or (tmeta.get("subagentSpec") is not None):
                        continue

                    ls_status = str(traj.get("status", ""))
                    term_reason = str(traj.get("latestExecutorTerminationReason", ""))
                    ls_mtime = self._parse_iso_timestamp(traj.get("lastModifiedTime", ""))
                    latest_ts = max(ls_mtime, eff_mtime)

                    is_running = (ls_status == "CASCADE_RUN_STATUS_RUNNING") or (session_id in running_roots)
                    is_recent_error = (
                        ls_status == "CASCADE_RUN_STATUS_IDLE"
                        and term_reason == "EXECUTOR_TERMINATION_REASON_ERROR"
                        and (now - latest_ts) <= error_grace_seconds
                        and (not tail_info["cleanly_finished"])
                    )

                    if is_running:
                        if (now - latest_ts) > running_cap:
                            continue
                    elif is_recent_error:
                        pass
                    else:
                        # CASCADE_RUN_STATUS_IDLE + NO_TOOL_CALL / USER_CANCELED / 过期 ERROR -> 坚决跳过
                        continue
                else:
                    if (now - eff_mtime) > fallback_cap:
                        continue
                    if not self.is_root_user_session(session_id):
                        continue
                    active_subs_fb = self.get_active_subagents_for_session(
                        sess_path,
                        max_idle=fallback_cap,
                        live_trajectories=None,
                    )
                    if tail_info["cleanly_finished"] and not active_subs_fb:
                        continue

                # 防重复接力拦截：仅拦截尾部正在等待响应的同款接力指令
                if self.is_session_waiting_for_recovery(transcript_path):
                    continue

                last_user_prompt = ""
                subagents_invoked = []
                for line in lines:
                    try:
                        d = json.loads(line)
                        if d.get("source") == "USER_EXPLICIT" and d.get("type") == "USER_INPUT":
                            clean_c = d.get("content", "").replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()
                            if "<ADDITIONAL_METADATA>" in clean_c:
                                clean_c = clean_c.split("<ADDITIONAL_METADATA>")[0].strip()
                            last_user_prompt = clean_c[:180].replace("\n", " ")
                        for tc in d.get("tool_calls", []):
                            if tc.get("name") == "invoke_subagent":
                                args = tc.get("args") or {}
                                role = args.get("Role") or args.get("TypeName")
                                if role and role not in subagents_invoked:
                                    subagents_invoked.append(role)
                    except Exception:
                        pass

                active_subs = self.get_active_subagents_for_session(
                    sess_path,
                    max_idle=max_idle_seconds,
                    live_trajectories=live_trajectories if has_live_ls else None,
                )
                has_active_subs = len(active_subs) > 0

                active_sessions.append({
                    "session_id": session_id,
                    "session_dir": sess_path,
                    "transcript_path": transcript_path,
                    "last_modified": eff_mtime,
                    "last_user_prompt": last_user_prompt,
                    "subagents": subagents_invoked,
                    "active_subagents": active_subs,
                    "has_active_subagents": has_active_subs
                })
            except Exception:
                continue

        active_sessions.sort(key=lambda x: x["last_modified"], reverse=True)
        return active_sessions

    def pre_switch_snapshot(self) -> List[Dict[str, Any]]:
        """在物理切号杀进程前瞬间锁定当前真正活跃的根会话列表（即使 0 个也显式落盘标记）"""
        sessions = self.scan_active_sessions()
        try:
            snap_dir = os.path.dirname(os.path.abspath(self.snapshot_path))
            os.makedirs(snap_dir, exist_ok=True)
            payload = {
                "schema": 2,
                "captured_at": time.time(),
                "sessions": sessions,
            }
            tmp_path = f"{self.snapshot_path}.tmp.{os.getpid()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.snapshot_path)
            logger.info(f"📸 [轮换前快照] 精准锁定 {len(sessions)} 个真正活跃的主会话 -> {self.snapshot_path}")
        except Exception as e:
            logger.error(f"❌ 写入快照失败: {e}")
        return sessions

    def build_teamwork_resume_prompt(self, session_info: Optional[Dict[str, Any]] = None, base_prompt: str = "") -> str:
        """构建精简有力的系统接力提示词：恢复一切中断的任务和子代理"""
        if base_prompt:
            return base_prompt

        last_req = (session_info.get("last_user_prompt", "").strip() if session_info else "")
        subagents = (session_info.get("subagents", []) if session_info else [])
        subs_hint = f"（重点协同子代理: {'、'.join(subagents)}）" if subagents else ""

        if last_req:
            clean_req = last_req if len(last_req) <= 120 else f"{last_req[:117]}..."
            return (
                f"<USER_REQUEST>\n"
                f"【配额已就绪】请恢复一切中断的任务和子代理{subs_hint}，继续推进断点工作:\n"
                f"「{clean_req}」\n"
                f"</USER_REQUEST>"
            )
        else:
            return (
                f"<USER_REQUEST>\n"
                f"【配额已就绪】请恢复一切中断的任务和子代理{subs_hint}，继续全速推进直至完成。\n"
                f"</USER_REQUEST>"
            )

    def deliver_resume_message_to_session(
        self,
        session_id: str,
        prompt: str,
        title: str = "恢复一切中断的任务和子代理"
    ) -> bool:
        """
        【官方原生 IPC 消息投递与唤醒】
        调用 language_server agentapi send-message --title=... <session_id> <prompt>
        """
        if not LANGUAGE_SERVER_BIN:
            logger.error("❌ 未找到 language_server 二进制文件，无法投递接力消息")
            return False

        # 防抖锁：同一 Session 15s 内不重复投递
        lock_dir = "/tmp/.antigravity_recovery_locks"
        os.makedirs(lock_dir, exist_ok=True)
        lock_file = os.path.join(lock_dir, f"{session_id}.lock")
        now_ts = time.time()
        if os.path.exists(lock_file):
            try:
                if now_ts - os.path.getmtime(lock_file) < 15.0:
                    logger.info(f"🛡️ [防抖拦截] 会话 {session_id} 15s 内已投递过接力消息，跳过")
                    return True
            except Exception:
                pass

        cmd = [LANGUAGE_SERVER_BIN, "agentapi", "send-message", f"--title={title}", session_id, prompt]
        for attempt in range(1, 4):
            try:
                exec_env = self.get_execution_env()
                res = subprocess.run(cmd, capture_output=True, text=True, env=exec_env, timeout=10)
                if res.returncode == 0 and ("sendMessage" in res.stdout or "success" in res.stdout.lower() or not res.stderr):
                    try:
                        with open(lock_file, "w") as f:
                            f.write(str(now_ts))
                    except Exception:
                        pass
                    logger.info(f"🎉 [原生IPC接力成功] 成功向会话 {session_id[:12]} 投递断点续传指令！")
                    return True
                else:
                    logger.warning(f"⚠️ 投递接力消息失败 (尝试 {attempt}/3): code={res.returncode}, out={res.stdout}, err={res.stderr}")
                    time.sleep(1.0)
            except Exception as e:
                logger.warning(f"⚠️ 投递接力消息异常 (尝试 {attempt}/3): {e}")
                time.sleep(1.0)

        return False

    def batch_recover_all_working_sessions(
        self,
        prompt: str = "",
        preloaded_sessions: Optional[List[Dict[str, Any]]] = None
    ) -> int:
        """
        【换号后批量唤醒】
        - 优先使用传入的 preloaded_sessions 或切号前捕获的快照（严格尊重 0 会话空快照，绝不触发重扫描误唤醒）；
        - 快照超过 120s 视为过期失效；仅当完全无有效快照时才实时扫描；
        """
        snapshot_loaded = False
        sessions_to_recover: List[Dict[str, Any]] = []

        if preloaded_sessions is not None:
            sessions_to_recover = list(preloaded_sessions)
            snapshot_loaded = True
            if os.path.isfile(self.snapshot_path):
                try:
                    os.remove(self.snapshot_path)
                except Exception:
                    pass
        elif os.path.isfile(self.snapshot_path):
            try:
                snap_mtime = os.path.getmtime(self.snapshot_path)
                with open(self.snapshot_path, "r", encoding="utf-8") as f:
                    raw_snap = json.load(f)
                os.remove(self.snapshot_path)
                now_t = time.time()
                if isinstance(raw_snap, dict) and "sessions" in raw_snap:
                    captured_at = float(raw_snap.get("captured_at") or snap_mtime)
                    if (now_t - captured_at) <= 120.0:
                        sessions_to_recover = list(raw_snap.get("sessions") or [])
                        snapshot_loaded = True
                    else:
                        logger.info("ℹ️ 切号快照已超过 120s 时效窗口，已丢弃")
                elif isinstance(raw_snap, list):
                    if (now_t - snap_mtime) <= 120.0:
                        sessions_to_recover = raw_snap
                        snapshot_loaded = True
            except Exception as ex:
                logger.warning(f"⚠️ 读取切号前快照失败: {ex}")

        if not snapshot_loaded:
            sessions_to_recover = self.scan_active_sessions()

        if not sessions_to_recover:
            logger.info("ℹ️ 当前无在途中断会话需要唤醒 (0 个，已尊重精准快照)")
            return 0

        success_count = 0
        for sess in sessions_to_recover:
            sid = sess.get("session_id")
            if not sid:
                continue
            resume_prompt = self.build_teamwork_resume_prompt(session_info=sess, base_prompt=prompt)
            if self.deliver_resume_message_to_session(sid, resume_prompt):
                success_count += 1

        logger.info(f"🎉 批量断点接力投递完成：成功接力 {success_count}/{len(sessions_to_recover)} 个会话")
        return success_count

    def relay_all_active_sessions(self, prompt: str = "") -> int:
        """兼容旧接口"""
        return self.batch_recover_all_working_sessions(prompt=prompt)
