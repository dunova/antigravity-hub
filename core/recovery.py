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
import subprocess
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

    def get_effective_session_mtime(self, session_dir: str, root_mtime: float) -> float:
        """向上穿透统计所有在途 Subagents 的最新活跃时间"""
        eff_mtime = root_mtime
        sub_dir = os.path.join(session_dir, ".system_generated", "subagents")
        if os.path.isdir(sub_dir):
            for fname in os.listdir(sub_dir):
                if fname.endswith(".json"):
                    sub_id = fname[:-5]
                    sub_tpath = os.path.join(self.brain_dir, sub_id, ".system_generated", "logs", "transcript.jsonl")
                    if os.path.exists(sub_tpath):
                        try:
                            sm = os.path.getmtime(sub_tpath)
                            if sm > eff_mtime:
                                eff_mtime = sm
                        except Exception:
                            pass
        return eff_mtime

    def check_subagent_is_active(self, sub_session_id: str) -> bool:
        """检查单个子代理会话是否仍处于活跃或未完成状态"""
        sub_tpath = os.path.join(self.brain_dir, sub_session_id, ".system_generated", "logs", "transcript.jsonl")
        if not os.path.isfile(sub_tpath):
            return False

        try:
            mtime = os.path.getmtime(sub_tpath)
            if time.time() - mtime > 1800:
                return False

            with open(sub_tpath, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
            if not lines:
                return False

            for l in reversed(lines[-25:]):
                try:
                    d = json.loads(l)
                    ttype = d.get("type", "")
                    if ttype in ("USER_INPUT", "PLANNER_RESPONSE"):
                        if ttype == "PLANNER_RESPONSE":
                            tcalls = d.get("tool_calls", [])
                            content = str(d.get("content", "")).strip()
                            if len(tcalls) == 0 and bool(content):
                                return False
                            if len(tcalls) > 0:
                                return True
                        elif ttype == "USER_INPUT":
                            return True
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"检查子代理 {sub_session_id} 异常: {e}")

        return False

    def get_active_subagents_for_session(self, session_dir: str) -> List[str]:
        """探测主会话下属正在运行的 Subagents ID 列表"""
        active_subs = []
        sub_dir = os.path.join(session_dir, ".system_generated", "subagents")
        if not os.path.isdir(sub_dir):
            return active_subs

        for fname in os.listdir(sub_dir):
            if fname.endswith(".json"):
                sub_id = fname[:-5]
                if self.check_subagent_is_active(sub_id):
                    active_subs.append(sub_id)

        return active_subs

    def scan_active_sessions(self, max_idle_seconds: int = 2700) -> List[Dict[str, Any]]:
        """扫描 brain 目录，识别最近活跃且未完工的主会话"""
        if not os.path.exists(self.brain_dir):
            return []

        active_sessions = []
        now = time.time()

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
                mtime = os.path.getmtime(transcript_path)
                eff_mtime = self.get_effective_session_mtime(sess_path, mtime)
                if (now - eff_mtime) > max_idle_seconds:
                    continue

                with open(transcript_path, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f if l.strip()]
                if len(lines) < 3:
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

                last_major_type = ""
                last_major_content = ""
                last_major_tool_calls = []
                for tl in reversed(lines[-50:]):
                    try:
                        td = json.loads(tl)
                        ttype = td.get("type", "")
                        if ttype in ("EPHEMERAL_MESSAGE", "GENERIC", "ERROR_MESSAGE", "CHECKPOINT", "SYSTEM_MESSAGE"):
                            continue
                        if ttype in ("PLANNER_RESPONSE", "USER_INPUT"):
                            last_major_type = ttype
                            last_major_content = str(td.get("content", ""))
                            last_major_tool_calls = td.get("tool_calls", [])
                            break
                    except Exception:
                        continue

                active_subs = self.get_active_subagents_for_session(sess_path)
                has_active_subs = len(active_subs) > 0

                # 必须是根主会话，坚决过滤子代理
                if not self.is_root_user_session(session_id):
                    continue

                # 已完工会话物理拦截跳过
                if last_major_type == "PLANNER_RESPONSE" and len(last_major_tool_calls) == 0 and bool(last_major_content.strip()) and not has_active_subs:
                    continue

                # 防重复接力拦截
                if "断点接力指令" in last_major_content or "系统配额轮换完成" in last_major_content:
                    continue

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
        """在物理切号杀进程前瞬间锁定当前活跃主会话列表"""
        sessions = self.scan_active_sessions(max_idle_seconds=2700)
        try:
            os.makedirs(os.path.dirname(self.snapshot_path), exist_ok=True)
            with open(self.snapshot_path, "w", encoding="utf-8") as f:
                json.dump(sessions, f, indent=2, ensure_ascii=False)
            logger.info(f"📸 [轮换前快照] 成功锁定 {len(sessions)} 个活跃主会话 -> {self.snapshot_path}")
        except Exception as e:
            logger.error(f"❌ 写入快照失败: {e}")
        return sessions

    def build_teamwork_resume_prompt(self, session_info: Optional[Dict[str, Any]] = None, base_prompt: str = "") -> str:
        """构建包含 Teamwork 恢复保证的系统接力提示词"""
        if base_prompt:
            return base_prompt

        last_req = (session_info.get("last_user_prompt", "") if session_info else "")
        subagents = (session_info.get("subagents", []) if session_info else [])
        has_active_subs = (session_info.get("has_active_subagents", False) if session_info else False)

        is_teamwork = (
            has_active_subs
            or len(subagents) > 0
            or any(k in last_req.lower() for k in ["teamwork", "子代理", "多智能体", "subagent", "协同"])
        )

        if is_teamwork:
            sub_roles_str = "、".join(subagents) if subagents else "团队在途子代理"
            return (
                f"<USER_REQUEST>\n"
                f"【配额轮换完成 · Teamwork 多智能体断点恢复接力指令】\n"
                f"系统配额与网络已全面重载就绪，充足算力已就位！\n"
                f"检测到本会话正在执行【Teamwork 多智能体工程协作】任务，上一条用户指令在协同推进途中遭遇意外中断:\n"
                f"「{last_req}」\n\n"
                f"🎯 请立即无缝恢复 Teamwork 协同管线并推进以下动作:\n"
                f"1. 【恢复 Teamwork 团队协作】：立即检查分配给各子代理（Subagents: {sub_roles_str}）的任务进度与存活状态；\n"
                f"2. 【驱动唤醒未完工子任务】：若子代理执行被中断或尚未交付，重新拉起或发送消息驱动其继续推进，严禁丢弃未完工的协同分支；\n"
                f"3. 【全速推进主线工程】：耐心地完成刚才被中断的代码编写、界面修复、终端命令或联调任务，确保每一处业务逻辑真实落地；\n"
                f"4. 【闭环汇总与交付】：等待或汇总各子代理产出成果，严格按照工程规范落盘交底文档与更新总账，完成最终交付。\n"
                f"</USER_REQUEST>"
            )
        else:
            return (
                f"<USER_REQUEST>\n"
                f"【配额轮换完成 · 断点全速续跑指令】\n"
                f"系统配额与网络已重载就绪，充足算力已就位！\n"
                f"检测到本会话上一条用户指令在执行中途遭遇意外中断:\n"
                f"「{last_req}」\n\n"
                f"🎯 请从刚才中断的断点继续全速推进:\n"
                f"1. 【全速推进实体工程】：耐心地继续完成刚才被中断的代码编写、终端命令或联调任务，确保业务逻辑与功能真实落地；\n"
                f"2. 【恢复协作分支（若涉及）】：若任务涉及子代理（Subagents），检查并唤醒所有未完工子代理继续推进；\n"
                f"3. 【严谨闭环交付】：在所有核心功能彻底完成并通过验证后，按交付门禁落盘技术交底与更新总账，保持无人值守直到任务彻底高质量闭环。\n"
                f"</USER_REQUEST>"
            )

    def deliver_resume_message_to_session(
        self,
        session_id: str,
        prompt: str,
        title: str = "系统额度轮换完成·无感知自动接力"
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

    def batch_recover_all_working_sessions(self, prompt: str = "") -> int:
        """
        【换号后批量唤醒】优先读取切号前瞬间记录的快照；若无快照则实时扫描活跃主会话并依次投递原生接力指令。
        """
        sessions_to_recover = []
        if os.path.isfile(self.snapshot_path):
            try:
                with open(self.snapshot_path, "r", encoding="utf-8") as f:
                    sessions_to_recover = json.load(f)
                os.remove(self.snapshot_path)
            except Exception:
                pass

        if not sessions_to_recover:
            sessions_to_recover = self.scan_active_sessions(max_idle_seconds=2700)

        if not sessions_to_recover:
            logger.info("ℹ️ 当前未发现需要恢复的活跃会话")
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
