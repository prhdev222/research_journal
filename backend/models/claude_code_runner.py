"""
claude_code_runner.py — รัน claude -p subprocess
ใช้ Claude Code auth โดยตรง ไม่ต้อง API key

Features:
- stream text chunks
- session_id tracking (resume agent chat)
- allowed tools (WebSearch, WebFetch, ฯลฯ)
- named sub-agents via --agents
"""
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator

CLAUDE_BIN = "/opt/homebrew/bin/claude"
PROJECT_DIR = str(Path(__file__).parent.parent.parent)  # ~/projects/research-assistant


@dataclass
class AgentEvent:
    type: str           # "chunk" | "tool_use" | "done" | "error"
    data: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    session_id: str = ""


async def stream_events(
    prompt: str,
    system_prompt: str = "",
    model: str = "claude-sonnet-4-6",
    allowed_tools: list[str] | None = None,
    resume_session: str | None = None,
    agents_def: dict | None = None,       # {"name": {"description":"..","prompt":".."},...}
    no_persist: bool = True,
) -> AsyncGenerator[AgentEvent, None]:
    """
    Yield AgentEvents จาก claude -p stream-json
    """
    cmd = [
        CLAUDE_BIN, "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model", model,
        "--permission-mode", "bypassPermissions",
    ]
    if no_persist:
        cmd += ["--no-session-persistence"]
    if system_prompt:
        cmd += ["--append-system-prompt", system_prompt]
    if allowed_tools:
        cmd += ["--allowedTools", ",".join(allowed_tools)]
    if resume_session:
        cmd += ["--resume", resume_session]
        cmd = [c for c in cmd if c != "--no-session-persistence"]  # ลบออกถ้า resume
    if agents_def:
        cmd += ["--agents", json.dumps(agents_def)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=PROJECT_DIR,   # sessions เก็บใน research-assistant project dir
        )
    except FileNotFoundError:
        yield AgentEvent("error", data=f"Claude CLI not found at {CLAUDE_BIN}")
        return

    session_id = ""
    seen_text = ""
    error_text = ""

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")

        # จับ session_id จาก init event
        if etype == "system" and event.get("subtype") == "init":
            session_id = event.get("session_id", "")

        # text chunks (streaming)
        elif etype == "assistant":
            if event.get("error"):
                error_text = event.get("error") or "Claude CLI error"
                continue
            for block in event.get("message", {}).get("content", []):
                btype = block.get("type")
                if btype == "text":
                    chunk = block["text"]
                    if chunk.startswith(seen_text):
                        new_part = chunk[len(seen_text):]
                        if new_part:
                            yield AgentEvent("chunk", data=new_part, session_id=session_id)
                            seen_text = chunk
                    else:
                        yield AgentEvent("chunk", data=chunk, session_id=session_id)
                        seen_text = chunk

                elif btype == "tool_use":
                    yield AgentEvent(
                        "tool_use",
                        tool_name=block.get("name", ""),
                        tool_input=block.get("input", {}),
                        session_id=session_id,
                    )

        # final result (fallback ถ้า partial messages ไม่ครบ)
        elif etype == "result":
            result_text = event.get("result", "")
            if event.get("is_error"):
                error_text = result_text or error_text or "Claude CLI returned an error"
                yield AgentEvent("error", data=error_text, session_id=session_id)
                yield AgentEvent("done", session_id=session_id)
                continue
            if not seen_text:
                if result_text:
                    yield AgentEvent("chunk", data=result_text, session_id=session_id)
            yield AgentEvent("done", session_id=session_id)

    stderr = await proc.stderr.read() if proc.stderr else b""
    code = await proc.wait()
    if code != 0 and not error_text:
        detail = stderr.decode("utf-8", errors="replace").strip()
        yield AgentEvent("error", data=detail or f"Claude CLI exited with code {code}", session_id=session_id)


async def run(
    prompt: str,
    system_prompt: str = "",
    model: str = "claude-sonnet-4-6",
    allowed_tools: list[str] | None = None,
    resume_session: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream text chunks เท่านั้น (simplified)"""
    async for ev in stream_events(prompt, system_prompt, model, allowed_tools, resume_session):
        if ev.type == "chunk":
            yield ev.data


async def run_with_session(
    prompt: str,
    system_prompt: str = "",
    model: str = "claude-sonnet-4-6",
    allowed_tools: list[str] | None = None,
    resume_session: str | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    """Stream AgentEvents พร้อม session_id (สำหรับ chat feature)"""
    async for ev in stream_events(prompt, system_prompt, model, allowed_tools, resume_session, no_persist=False):
        yield ev


async def call(
    prompt: str,
    system_prompt: str = "",
    model: str = "claude-sonnet-4-6",
    allowed_tools: list[str] | None = None,
) -> str:
    """One-shot call — คืน full text"""
    full = ""
    async for ev in stream_events(prompt, system_prompt, model, allowed_tools):
        if ev.type == "chunk":
            full += ev.data
        elif ev.type == "error":
            raise RuntimeError(ev.data)
    return full
