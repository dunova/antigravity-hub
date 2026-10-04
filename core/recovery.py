#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/recovery.py - Antigravity 多会话精准嗅探与零 UI 侵入断点接力中枢
=====================================================================
核心契约：
1. 100% 拔除 AppleScript 模拟物理按键，根治输入法乱码；
2. 物理底座级多会话嗅探 (Active Session Sniffer)：遍历扫描 brain transcripts；
3. 已完结会话物理拦截跳过门禁 (Finished Task Filter)：主任务交付且无存活子代理时绝对不唤醒；
4. Teamwork 多智能体专属断点恢复提示词引擎：自动提取分配子代理角色并强令恢复协同管线；
5. 零 UI 侵入原生消息队列投递 (Zero-UI Injection)：直接投递至系统消息队列并触发语言服务器。
"""

import os
import sys
import time
import json
import glob
import re
import uuid
import logging
import subprocess
from typing import Dict, Any, List, Optional

logger = logging.getLogger("SessionRecovery")

DEFAULT_BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")
DEFAULT_AGENTAPI_BIN = os.path.expanduser("~/.gemini/antigravity/bin/agentapi")


class AntigravitySessionRecoveryManager:
    """会话嗅探与断点接力管理器"""

    def __init__(self, brain_dir: str = DEFAULT_BRAIN_DIR):
        self.brain_dir = brain_dir

    def detect_live_ls_env(self) -> Dict[str, str]:
        """
        动态嗅探运行中的 language_server 进程，提取监听端口与 CSRF Token。
        """
        env = {}
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
                return {}

            lsof_out = subprocess.check_output(
                ["lsof", "-nP", "-a", "-iTCP", "-sTCP:LISTEN", "-p", ls_pid],
                text=True
            )
            ports = []
            for l in lsof_out.splitlines():
                m = re.search(r":(\d+)\s+\(LISTEN\)", l)
                if m:
                    ports.append(m.group(1))

            for p in sorted(ports, reverse=True):
                env["ANTIGRAVITY_LS_ADDRESS"] = f"127.0.0.1:{p}"
                env["ANTIGRAVITY_CSRF_TOKEN"] = csrf
                env["ANTIGRAVITY_LS_PID"] = ls_pid
                return env

        except Exception as e:
            logger.debug(f"嗅探 language_server 异常: {e}")

        return env

    def get_effective_session_mtime(self, session_dir: str, root_mtime: float) -> float:
        """
        【子代理活跃向上穿透】
        在 Teamwork / 多智能体架构下，主会话等待子代理时自身 transcript 不会频繁更新；
        必须向上穿透统计其所有在途 Subagents 的最新活跃时间。
        """
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
                    # 二级嵌套子代理穿透（Coordinator -> Orchestrator -> Workers）
                    sub_nested = os.path.join(self.brain_dir, sub_id, ".system_generated", "subagents")
                    if os.path.isdir(sub_nested):
                        for n_fname in os.listdir(sub_nested):
                            if n_fname.endswith(".json"):
                                nid = n_fname[:-5]
                                ntpath = os.path.join(self.brain_dir, nid, ".system_generated", "logs", "transcript.jsonl")
                                if os.path.exists(ntpath):
                                    try:
                                        nm = os.path.getmtime(ntpath)
                                        if nm > eff_mtime:
                                            eff_mtime = nm
                                    except Exception:
                                        pass
        return eff_mtime

    def check_subagent_is_active(self, sub_session_id: str) -> bool:
        """
        强类型检查单个子代理会话是否仍处于活跃或未完成状态
        """
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
        """探测主会话及其下属所有正在全速运行或尚未交付的 Subagents ID 列表"""
        active_subs = []
        sub_dir = os.path.join(session_dir, ".system_generated", "subagents")
        if not os.path.isdir(sub_dir):
            return active_subs

        for fname in os.listdir(sub_dir):
            if fname.endswith(".json"):
                sub_id = fname[:-5]
                if self.check_subagent_is_active(sub_id):
                    active_subs.append(sub_id)
                nested_dir = os.path.join(self.brain_dir, sub_id, ".system_generated", "subagents")
                if os.path.isdir(nested_dir):
                    for n_fname in os.listdir(nested_dir):
                        if n_fname.endswith(".json"):
                            nid = n_fname[:-5]
                            if self.check_subagent_is_active(nid) and nid not in active_subs:
                                active_subs.append(nid)

        return active_subs

    def scan_active_sessions(self, max_idle_seconds: int = 2700) -> List[Dict[str, Any]]:
        """
        扫描 brain 目录，识别最近活跃且未完工的会话（已实装已完结过滤与子代理活跃穿透）。
        """
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
                                # 提取角色名
                                args = tc.get("args") or {}
                                for sub in args.get("Subagents", []):
                                    if isinstance(sub, dict):
                                        role = sub.get("Role") or sub.get("TypeName")
                                        if role and role not in subagents_invoked:
                                            subagents_invoked.append(role)
                    except Exception:
                        pass

                # 逆序查找最后一个主体事件
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

                # 探测活跃子代理
                active_subs = self.get_active_subagents_for_session(sess_path)
                has_active_subs = len(active_subs) > 0

                # 核心过滤：已完工会话物理拦截跳过
                if last_major_type == "PLANNER_RESPONSE" and len(last_major_tool_calls) == 0 and bool(last_major_content.strip()) and not has_active_subs:
                    logger.debug(f"🟢 [已完工跳过] 会话 {session_id[:12]} 任务已彻底完成闭环，坚决不唤醒！")
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
                f"系统配额与网络已全面重载就绪。\n"
                f"检测到本会话正在执行【Teamwork 多智能体工程协作】任务，上一条用户指令在协同推进途中遭遇意外中断:\n"
                f"「{last_req}」\n\n"
                f"🎯 请立即无缝恢复 Teamwork 协同管线并推进以下动作:\n"
                f"1. 【恢复 Teamwork 团队协作】：立即检查分配给各子代理（Subagents: {sub_roles_str}）的任务进度与存活状态；\n"
                f"2. 【驱动未完工子任务】：若子代理执行被中断或尚未交付，重新拉起或发送消息驱动其继续推进，严禁丢弃未完工的协同分支；\n"
                f"3. 【闭环汇总与交付】：等待或汇总各子代理产出成果，严格按照工程规范落盘交底文档与更新总账，完成最终交付。\n"
                f"</USER_REQUEST>"
            )
        else:
            return (
                f"<USER_REQUEST>\n"
                f"【配额轮换完成 · 断点接力指令】\n"
                f"系统配额与网络已重载就绪。\n"
                f"检测到本会话上一条用户指令在执行中途遭遇意外中断:\n"
                f"「{last_req}」\n\n"
                f"请从刚才中断的断点继续全速推进:\n"
                f"1. 恢复刚才被中断的代码编写、终端命令或调试任务；\n"
                f"2. 严格遵循交付门禁与工程规范，完成实测验证并在项目运维/文档目录落盘技术交底；\n"
                f"3. 保持无人值守直到任务完全闭环。\n"
                f"</USER_REQUEST>"
            )

    def inject_resume_message(self, session_id: str, prompt: str) -> bool:
        """
        零 UI 侵入：直接向 session 的 .system_generated/messages 投递系统消息，
        并在 undelivered 建立消费指针，由底层核心无感知触发唤醒。
        """
        sess_dir = os.path.join(self.brain_dir, session_id)
        if not os.path.isdir(sess_dir):
            logger.error(f"会话目录不存在: {sess_dir}")
            return False

        msg_id = str(uuid.uuid4())
        messages_dir = os.path.join(sess_dir, ".system_generated", "messages")
        undelivered_dir = os.path.join(messages_dir, "undelivered")

        try:
            os.makedirs(messages_dir, exist_ok=True)
            os.makedirs(undelivered_dir, exist_ok=True)

            msg_file = os.path.join(messages_dir, f"{msg_id}.json")
            pointer_file = os.path.join(undelivered_dir, msg_id)

            payload = {
                "id": msg_id,
                "sender": "system",
                "recipient": session_id,
                "content": prompt,
                "timestamp": int(time.time()),
                "type": "USER_INPUT"
            }

            with open(msg_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            with open(pointer_file, "w", encoding="utf-8") as f:
                f.write(msg_id)

            logger.info(f"📨 [零UI投递] 成功向会话 {session_id} 投递接力指令 (Message ID: {msg_id})")
            return True
        except Exception as e:
            logger.error(f"❌ 投递接力消息失败: {e}")
            return False

    def relay_all_active_sessions(self, prompt: str = "") -> int:
        """为所有当前活跃且未完结会话执行断点续传接力"""
        active_list = self.scan_active_sessions()
        if not active_list:
            logger.info("ℹ️ 当前未发现需要恢复的未闭环会话")
            return 0

        success_count = 0
        for sess in active_list:
            sid = sess["session_id"]
            resume_prompt = self.build_teamwork_resume_prompt(session_info=sess, base_prompt=prompt)
            if self.inject_resume_message(sid, resume_prompt):
                success_count += 1

        logger.info(f"🎉 断点接力投递完成：成功接力 {success_count}/{len(active_list)} 个会话")
        return success_count
