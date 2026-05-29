"""
main.py — FastAPI app
- SSE pipeline streaming
- Agent chat (resume session)
- Agent meeting mode
- Session + memory storage in SQLite
"""
import json
import uuid
from pathlib import Path
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from .auth import verify_password, create_token, verify_token
from .db.database import init_db, get_db
from .orchestrator import run_pipeline
from .models.claude_code_runner import run_with_session
from .models.provider_adapters import call_gemini, call_openrouter, call_zai
from .agents.registry import AGENT_PROFILES, get_profile, with_identity
from .utils.model_router import list_providers
from .agents.output import generate_analysis_py, generate_literature_md, generate_proposal_docx

app = FastAPI(title="AI Research Assistant")

FRONTEND = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


# ──────────────────────────────────────────────
# Startup
# ──────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await init_db()


# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────
class LoginBody(BaseModel):
    password: str

@app.post("/api/login")
async def login(body: LoginBody, response: Response):
    if not verify_password(body.password):
        raise HTTPException(status_code=401, detail="Wrong password")
    token = create_token()
    response.set_cookie("token", token, httponly=True, samesite="strict")
    return {"ok": True}

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("token")
    return {"ok": True}


# ──────────────────────────────────────────────
# Projects
# ──────────────────────────────────────────────
class NewProject(BaseModel):
    title: str
    topic: str
    agent_models: dict = Field(default_factory=dict, alias="model_config")
    journal_target: str | None = None   # "blood" | "bjh" | "haematologica" | "annals"

@app.post("/api/projects")
async def create_project(body: NewProject, token=Depends(verify_token)):
    pid = str(uuid.uuid4())
    cfg = body.agent_models.copy()
    if body.journal_target:
        cfg["writing_journal"] = body.journal_target
    async with await get_db() as db:
        await db.execute(
            "INSERT INTO projects (id, title, topic, model_config) VALUES (?,?,?,?)",
            (pid, body.title, body.topic, json.dumps(cfg)),
        )
        await db.commit()
    return {"id": pid}

@app.get("/api/projects")
async def list_projects(token=Depends(verify_token)):
    async with await get_db() as db:
        cur = await db.execute(
            "SELECT id,title,topic,status,created_at FROM projects ORDER BY created_at DESC"
        )
        rows = await cur.fetchall()
    return [{"id":r[0],"title":r[1],"topic":r[2],"status":r[3],"created_at":r[4]} for r in rows]


# ──────────────────────────────────────────────
# Agent Memory helpers
# ──────────────────────────────────────────────
async def get_agent_memory(project_id: str | None, agent_name: str) -> str:
    if not project_id:
        return ""
    async with await get_db() as db:
        cur = await db.execute(
            "SELECT memory FROM agent_memories WHERE project_id=? AND agent_name=?",
            (project_id, agent_name),
        )
        row = await cur.fetchone()
    return row[0] if row and row[0] else ""


async def update_agent_memory(project_id: str, agent_name: str, content: str) -> None:
    if not content:
        return
    profile = get_profile(agent_name)
    # Keep existing memory and append new work log (newest at top for easy retrieval)
    existing = await get_agent_memory(project_id, agent_name)
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_entry = (
        f"[{timestamp}] Work completed as {profile.display_name}:\n"
        f"{content[:4000]}"
    )
    # Prepend new entry, cap total at 8000 chars so prompt stays reasonable
    combined = f"{new_entry}\n\n---\n{existing}" if existing else new_entry
    memory = (
        f"# {profile.display_name} ({profile.nickname}) — Durable Memory\n"
        f"Role: {profile.role}\n"
        f"Memory focus: {profile.memory_focus}\n\n"
        f"{combined[:8000]}"
    )
    async with await get_db() as db:
        await db.execute(
            """
            INSERT INTO agent_memories (project_id, agent_name, memory, updated_at)
            VALUES (?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(project_id, agent_name)
            DO UPDATE SET memory=excluded.memory, updated_at=CURRENT_TIMESTAMP
            """,
            (project_id, agent_name, memory),
        )
        await db.commit()


# ──────────────────────────────────────────────
# Pipeline (SSE)
# ──────────────────────────────────────────────
@app.get("/api/projects/{pid}/run")
async def run_project(pid: str, token=Depends(verify_token)):
    async with await get_db() as db:
        cur = await db.execute("SELECT topic, model_config FROM projects WHERE id=?", (pid,))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    topic, model_config = row

    async def event_stream():
        async for event in run_pipeline(topic, model_config):
            if event.get("event") == "agent_done":
                content = event.get("content", "")
                agent_name = event.get("agent", "")
                if content and agent_name:
                    # Use session_id from Claude Code if available; otherwise generate one
                    row_id = event.get("session_id") or str(uuid.uuid4())
                    async with await get_db() as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO sessions (id, project_id, role, agent_name, content) VALUES (?,?,?,?,?)",
                            (row_id, pid, "agent", agent_name, content),
                        )
                        await db.commit()
                    await update_agent_memory(pid, agent_name, content)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ──────────────────────────────────────────────
# Agent Chat
# ──────────────────────────────────────────────
class ChatMessage(BaseModel):
    message: str
    session_id: str | None = None
    agent_name: str = "literature"
    system_prompt: str = ""
    project_id: str | None = None

@app.post("/api/agents/chat")
async def agent_chat(body: ChatMessage, token=Depends(verify_token)):
    from .agents import (
        literature, research_question, study_design,
        irb_ethics, stats, writing, summary, deid
    )
    from .utils.model_router import get_model

    agent_map = {
        "literature":        (with_identity("literature", literature.SYSTEM),        literature.ALLOWED_TOOLS),
        "research_question": (with_identity("research_question", research_question.SYSTEM), None),
        "study_design":      (with_identity("study_design", study_design.SYSTEM),      None),
        "irb_ethics":        (with_identity("irb_ethics", irb_ethics.SYSTEM),        None),
        "stats":             (with_identity("stats", stats.SYSTEM),             None),
        "writing":           (with_identity("writing", writing.SYSTEM),           None),
        "summary":           (with_identity("summary", summary.SYSTEM),           None),
        "deid":              (with_identity("deid", deid.SYSTEM),              None),
    }

    sys_prompt, allowed_tools = agent_map.get(
        body.agent_name,
        ("You are a helpful research assistant.", None)
    )
    if body.system_prompt:
        sys_prompt = body.system_prompt

    memory = await get_agent_memory(body.project_id, body.agent_name)
    if memory:
        sys_prompt = f"{sys_prompt}\n\n# Your Memory\n{memory}"

    model = get_model(body.agent_name)

    async def chat_stream():
        full_response = ""
        async for ev in run_with_session(
            body.message,
            sys_prompt,
            model,
            allowed_tools=allowed_tools,
            resume_session=body.session_id,
        ):
            if ev.type == "chunk":
                full_response += ev.data
                yield f"data: {json.dumps({'type':'chunk','data':ev.data}, ensure_ascii=False)}\n\n"
            elif ev.type == "tool_use":
                yield f"data: {json.dumps({'type':'tool_use','tool':ev.tool_name,'input':ev.tool_input}, ensure_ascii=False)}\n\n"
            elif ev.type == "error":
                yield f"data: {json.dumps({'type':'error','data':ev.data}, ensure_ascii=False)}\n\n"
                return
            elif ev.type == "done":
                if body.project_id and full_response:
                    await update_agent_memory(body.project_id, body.agent_name, full_response)
                yield f"data: {json.dumps({'type':'done','session_id':ev.session_id}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(chat_stream(), media_type="text/event-stream")


# ──────────────────────────────────────────────
# Meeting helpers
# ──────────────────────────────────────────────
async def get_project_context(project_id: str, limit: int = 24000) -> str:
    async with await get_db() as db:
        cur = await db.execute(
            """
            SELECT agent_name, content
            FROM sessions
            WHERE project_id=? AND role='agent' AND content IS NOT NULL AND content != ''
            ORDER BY created_at
            """,
            (project_id,),
        )
        rows = await cur.fetchall()
    context = "\n\n".join(
        f"=== {agent.upper()} OUTPUT ===\n{content[-6000:]}"
        for agent, content in rows
        if content
    )
    return context[-limit:] if len(context) > limit else context


async def run_agent_once(
    project_id: str,
    agent_name: str,
    question: str,
    meeting_context: str,
) -> str:
    from .agents import (
        literature, research_question, study_design,
        irb_ethics, stats, writing, summary, deid
    )
    from .orchestrator import ORCHESTRATOR_SYSTEM
    from .utils.model_router import get_model

    systems = {
        "orchestrator": ORCHESTRATOR_SYSTEM,
        "literature": literature.SYSTEM,
        "research_question": research_question.SYSTEM,
        "study_design": study_design.SYSTEM,
        "irb_ethics": irb_ethics.SYSTEM,
        "stats": stats.SYSTEM,
        "writing": writing.SYSTEM,
        "summary": summary.SYSTEM,
        "deid": deid.SYSTEM,
        "output": (
            "You are the Output Agent. Review the project context and explain "
            "which concrete deliverables can be generated now, what inputs are "
            "still missing, and the next file-oriented action."
        ),
    }
    memory = await get_agent_memory(project_id, agent_name)
    prompt = (
        f"Meeting question:\n{question}\n\n"
        f"Project and meeting context:\n{meeting_context}\n\n"
        f"Your durable memory:\n{memory or '(none yet)'}\n\n"
        "Answer only from your agent role. Keep it concise. End with one practical recommendation."
    )
    response = ""
    async for ev in run_with_session(
        prompt,
        with_identity(agent_name, systems.get(agent_name, "")),
        get_model(agent_name),
    ):
        if ev.type == "chunk":
            response += ev.data
        elif ev.type == "error":
            raise RuntimeError(ev.data)
    return response


def _guest_row_to_dict(r) -> dict:
    return {
        "id": r[0], "name": r[1], "provider": r[2],
        "model": r[3] or None, "role": r[4] or "",
        "prompt": r[5] or "", "parent_agent": r[6] or None,
        # api_key at index 7 — never returned to browser
    }

async def get_guest_agents(guest_ids: list[str]) -> list[dict]:
    if not guest_ids:
        return []
    placeholders = ",".join("?" for _ in guest_ids)
    async with await get_db() as db:
        cur = await db.execute(
            f"SELECT id,name,provider,model,role,prompt,parent_agent "
            f"FROM guest_agents WHERE enabled=1 AND id IN ({placeholders})",
            tuple(guest_ids),
        )
        rows = await cur.fetchall()
    by_id = {r[0]: _guest_row_to_dict(r) for r in rows}
    return [by_id[gid] for gid in guest_ids if gid in by_id]


async def get_agent_team(agent_name: str) -> list[dict]:
    """Return all enabled team members assigned to this agent."""
    async with await get_db() as db:
        cur = await db.execute(
            "SELECT id,name,provider,model,role,prompt,parent_agent,api_key "
            "FROM guest_agents WHERE enabled=1 AND parent_agent=?",
            (agent_name,),
        )
        rows = await cur.fetchall()
    result = []
    for r in rows:
        d = _guest_row_to_dict(r)
        d["_api_key"] = r[7] or None   # internal use only
        result.append(d)
    return result


async def run_guest_once(
    guest: dict,
    question: str,
    meeting_context: str,
    parent_agent_name: str | None = None,
    parent_agent_profile=None,
) -> tuple[str, str]:
    """Run a guest/team-member AI. parent_agent_* give team context."""
    parent_label = ""
    if parent_agent_profile:
        parent_label = (
            f"You are a specialist team member in {parent_agent_profile.display_name}'s team "
            f"({parent_agent_profile.nickname}). "
            f"Your parent agent focuses on: {parent_agent_profile.role}\n"
        )
    system_prompt = (
        f"{parent_label}"
        f"Team member name: {guest['name']}\n"
        f"Your specialty/role: {guest.get('role') or 'External research assistant'}\n"
        f"Additional instructions: {guest.get('prompt') or 'Give a concise specialist perspective.'}\n\n"
        "Important: Do not expose API keys. If patient data appears, recommend de-identification."
    )
    prompt = (
        f"Meeting question:\n{question}\n\n"
        f"Context from the meeting so far:\n{meeting_context[-3000:]}\n\n"
        "Respond as this specialist team member. Be concise. "
        "Start your response by briefly identifying your specialty."
    )
    provider = guest["provider"]
    model = guest.get("model")
    api_key = guest.get("_api_key") or None   # from get_agent_team(); not from browser
    if provider == "openrouter":
        res = await call_openrouter(prompt, system_prompt, model, api_key)
        return res.text, res.model
    if provider == "gemini":
        res = await call_gemini(prompt, system_prompt, model, api_key)
        return res.text, res.model
    if provider == "zai":
        res = await call_zai(prompt, system_prompt, model, api_key)
        return res.text, res.model
    raise RuntimeError(f"Unsupported provider: {provider}")


# ──────────────────────────────────────────────
# Meeting endpoint  (Orra-led facilitation)
# ──────────────────────────────────────────────
class MeetingBody(BaseModel):
    question: str
    agent_names: list[str] = Field(default_factory=lambda: [
        "literature", "research_question", "study_design", "stats", "irb_ethics", "writing"
    ])
    guest_ids: list[str] = Field(default_factory=list)


def _parse_json_block(text: str) -> dict:
    try:
        s = text.find("{")
        e = text.rfind("}") + 1
        return json.loads(text[s:e])
    except Exception:
        return {}


@app.post("/api/projects/{pid}/meetings")
async def start_meeting(pid: str, body: MeetingBody, token=Depends(verify_token)):
    async with await get_db() as db:
        cur = await db.execute("SELECT id FROM projects WHERE id=?", (pid,))
        if not await cur.fetchone():
            raise HTTPException(404, "Project not found")

    meeting_id = str(uuid.uuid4())
    agents = [a for a in body.agent_names if a in AGENT_PROFILES and a != "orchestrator"]
    if not agents:
        agents = ["literature", "research_question", "study_design", "stats", "irb_ethics", "writing"]
    guests = await get_guest_agents(body.guest_ids)
    guest_labels = [f"guest:{g['name']}" for g in guests]
    orra = get_profile("orchestrator")

    async with await get_db() as db:
        await db.execute(
            "INSERT INTO meetings (id, project_id, question, agent_names, status) VALUES (?,?,?,?,?)",
            (meeting_id, pid, body.question, json.dumps(["orchestrator"] + agents + guest_labels), "running"),
        )
        await db.commit()

    async def meeting_stream():
        project_context = await get_project_context(pid)

        # ── Phase 1: Orra opens the meeting and sets agenda ───────────────────
        yield f"data: {json.dumps({'event':'orra_thinking','agent':'orchestrator','nickname':orra.nickname,'avatar':orra.avatar}, ensure_ascii=False)}\n\n"

        agent_list = ", ".join(agents)
        open_prompt = (
            f"You are chairing a research assistant meeting.\n\n"
            f"Meeting question: {body.question}\n\n"
            f"Available specialist agents: {agent_list}\n"
            + (f"Guest AI also present: {', '.join(g['name'] for g in guests)}\n" if guests else "")
            + f"\nProject context (brief):\n{project_context[:2500]}\n\n"
            "Your tasks:\n"
            "1. Write a brief opening statement welcoming the question (2 sentences).\n"
            "2. Choose 3-5 agents most relevant to this question.\n"
            "3. For each chosen agent, craft a specific sub-question or angle for them to address.\n\n"
            "Respond in JSON ONLY:\n"
            '{"opening": "...", "agenda": [{"agent": "literature", "angle": "What evidence supports..."}, ...]}'
        )
        open_raw = await run_agent_once(pid, "orchestrator", open_prompt, "")
        open_json = _parse_json_block(open_raw)
        opening_text = open_json.get("opening") or open_raw[:400]
        raw_agenda = open_json.get("agenda") or []
        agenda = [item for item in raw_agenda if item.get("agent") in agents]
        if not agenda:
            agenda = [{"agent": a, "angle": body.question} for a in agents]

        yield f"data: {json.dumps({'event':'orra_open','agent':'orchestrator','nickname':orra.nickname,'avatar':orra.avatar,'opening':opening_text,'agenda':agenda}, ensure_ascii=False)}\n\n"

        meeting_context = project_context
        transcript: list[tuple[str, str, str]] = []  # (agent, angle, content)

        # ── Phase 2: Round 1 — each agent + their team answers ──────────────
        for item in agenda:
            agent_name = item["agent"]
            angle = item.get("angle") or body.question
            profile = get_profile(agent_name)

            yield f"data: {json.dumps({'event':'turn_start','agent':agent_name,'nickname':profile.nickname,'avatar':profile.avatar,'angle':angle}, ensure_ascii=False)}\n\n"
            try:
                content = await run_agent_once(pid, agent_name, angle, meeting_context)
            except Exception as exc:
                yield f"data: {json.dumps({'event':'error','agent':agent_name,'data':str(exc)}, ensure_ascii=False)}\n\n"
                return
            turn_id = str(uuid.uuid4())
            async with await get_db() as db:
                await db.execute(
                    "INSERT INTO meeting_turns (id, meeting_id, round, agent_name, content) VALUES (?,?,?,?,?)",
                    (turn_id, meeting_id, 1, agent_name, content),
                )
                await db.commit()
            await update_agent_memory(pid, agent_name, f"Meeting Q: {body.question}\nMy angle: {angle}\n\n{content}")
            transcript.append((agent_name, angle, content))
            meeting_context += f"\n\n=== ROUND 1 · {agent_name.upper()} ===\nAngle: {angle}\n{content}"
            yield f"data: {json.dumps({'event':'turn_done','agent':agent_name,'nickname':profile.nickname,'avatar':profile.avatar,'angle':angle,'content':content}, ensure_ascii=False)}\n\n"

            # ── Team members of this agent speak right after ─────────────────
            team = await get_agent_team(agent_name)
            for member in team:
                member_key = f"team:{agent_name}:{member['id']}"
                yield f"data: {json.dumps({'event':'team_start','agent':member_key,'member_name':member['name'],'parent_agent':agent_name,'parent_nickname':profile.nickname,'parent_avatar':profile.avatar,'provider':member['provider']}, ensure_ascii=False)}\n\n"
                try:
                    member_content, model_used = await run_guest_once(
                        member, angle, meeting_context,
                        parent_agent_name=agent_name,
                        parent_agent_profile=profile,
                    )
                except Exception as exc:
                    yield f"data: {json.dumps({'event':'team_error','agent':member_key,'member_name':member['name'],'parent_agent':agent_name,'data':str(exc)}, ensure_ascii=False)}\n\n"
                    continue
                turn_id = str(uuid.uuid4())
                stored_name = f"[{profile.nickname}'s team] {member['name']} ({member['provider']})"
                async with await get_db() as db:
                    await db.execute(
                        "INSERT INTO meeting_turns (id, meeting_id, round, agent_name, content) VALUES (?,?,?,?,?)",
                        (turn_id, meeting_id, 1, stored_name, member_content),
                    )
                    await db.commit()
                meeting_context += f"\n\n=== [{profile.nickname}'s team] {member['name'].upper()} ===\n{member_content}"
                yield f"data: {json.dumps({'event':'team_done','agent':member_key,'member_name':member['name'],'parent_agent':agent_name,'parent_nickname':profile.nickname,'parent_avatar':profile.avatar,'model':model_used,'content':member_content}, ensure_ascii=False)}\n\n"

        # Guests in round 1
        for guest in guests:
            guest_key = f"guest:{guest['id']}"
            guest_label = f"Guest {guest['name']}"
            yield f"data: {json.dumps({'event':'turn_start','agent':guest_key,'nickname':guest_label,'avatar':'🤖','angle':body.question}, ensure_ascii=False)}\n\n"
            try:
                content, model_used = await run_guest_once(guest, body.question, meeting_context)
            except Exception as exc:
                yield f"data: {json.dumps({'event':'error','agent':guest_label,'data':str(exc)}, ensure_ascii=False)}\n\n"
                return
            stored_name = f"{guest_label} ({guest['provider']}{':' + model_used if model_used else ''})"
            turn_id = str(uuid.uuid4())
            async with await get_db() as db:
                await db.execute(
                    "INSERT INTO meeting_turns (id, meeting_id, round, agent_name, content) VALUES (?,?,?,?,?)",
                    (turn_id, meeting_id, 1, stored_name, content),
                )
                await db.commit()
            transcript.append((stored_name, body.question, content))
            meeting_context += f"\n\n=== ROUND 1 · {stored_name.upper()} ===\n{content}"
            yield f"data: {json.dumps({'event':'turn_done','agent':guest_key,'nickname':guest_label,'avatar':'🤖','angle':body.question,'content':content}, ensure_ascii=False)}\n\n"

        # ── Phase 3: Orra facilitates discussion ──────────────────────────────
        yield f"data: {json.dumps({'event':'orra_thinking','agent':'orchestrator','nickname':orra.nickname,'avatar':orra.avatar}, ensure_ascii=False)}\n\n"

        transcript_text = "\n\n".join(
            f"[{agent}] ({angle[:80]}):\n{content[:700]}"
            for agent, angle, content in transcript
        )
        valid_agent_names = [a for a, _, _ in transcript if not a.startswith("Guest")]
        disc_prompt = (
            f"You are chairing a research meeting.\n\n"
            f"Original question: {body.question}\n\n"
            f"Round 1 responses:\n{transcript_text}\n\n"
            "Facilitate a brief discussion:\n"
            "1. Note the key point of agreement or tension across responses.\n"
            "2. Ask ONE focused follow-up question to resolve the most important open point.\n"
            "3. Address it to 1-2 agents whose expertise is most relevant.\n\n"
            "Respond in JSON ONLY:\n"
            '{"observation": "...", "discussion_question": "...", "addressed_to": ["agent1"]}\n\n'
            f"Only use agents from: {valid_agent_names}"
        )
        disc_raw = await run_agent_once(pid, "orchestrator", disc_prompt, meeting_context)
        disc_json = _parse_json_block(disc_raw)
        observation = disc_json.get("observation") or disc_raw[:400]
        discussion_question = disc_json.get("discussion_question") or ""
        addressed_to = [a for a in (disc_json.get("addressed_to") or []) if a in valid_agent_names]

        yield f"data: {json.dumps({'event':'discussion_prompt','agent':'orchestrator','nickname':orra.nickname,'avatar':orra.avatar,'observation':observation,'question':discussion_question,'addressed_to':addressed_to}, ensure_ascii=False)}\n\n"

        # ── Phase 4: Round 2 — replies to Orra's discussion question ─────────
        if discussion_question and addressed_to:
            meeting_context += f"\n\n=== ORRA DISCUSSION QUESTION ===\n{discussion_question}"
            for agent_name in addressed_to:
                profile = get_profile(agent_name)
                yield f"data: {json.dumps({'event':'reply_start','agent':agent_name,'nickname':profile.nickname,'avatar':profile.avatar}, ensure_ascii=False)}\n\n"
                try:
                    reply = await run_agent_once(pid, agent_name, discussion_question, meeting_context)
                except Exception as exc:
                    yield f"data: {json.dumps({'event':'error','agent':agent_name,'data':str(exc)}, ensure_ascii=False)}\n\n"
                    continue
                turn_id = str(uuid.uuid4())
                async with await get_db() as db:
                    await db.execute(
                        "INSERT INTO meeting_turns (id, meeting_id, round, agent_name, content) VALUES (?,?,?,?,?)",
                        (turn_id, meeting_id, 2, agent_name, reply),
                    )
                    await db.commit()
                meeting_context += f"\n\n=== ROUND 2 · {agent_name.upper()} ===\n{reply}"
                yield f"data: {json.dumps({'event':'reply_done','agent':agent_name,'nickname':profile.nickname,'avatar':profile.avatar,'content':reply}, ensure_ascii=False)}\n\n"

        # ── Phase 5: Orra closes the meeting ──────────────────────────────────
        yield f"data: {json.dumps({'event':'orra_thinking','agent':'orchestrator','nickname':orra.nickname,'avatar':orra.avatar}, ensure_ascii=False)}\n\n"

        close_prompt = (
            f"Close this research meeting.\n\n"
            f"Original question: {body.question}\n\n"
            f"Full discussion:\n{meeting_context[-5000:]}\n\n"
            "Write a final synthesis (max 200 words):\n"
            "1. Main consensus\n"
            "2. Key recommendation / next action\n"
            "3. Open questions if any\n"
            "4. One closing sentence\n\n"
            "Write in flowing prose — no excessive bullet points."
        )
        try:
            closing_text = await run_agent_once(pid, "orchestrator", close_prompt, "")
        except Exception as exc:
            closing_text = f"(Error generating closing: {exc})"

        async with await get_db() as db:
            await db.execute(
                "UPDATE meetings SET status='done', summary=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (closing_text, meeting_id),
            )
            await db.commit()

        yield f"data: {json.dumps({'event':'orra_close','agent':'orchestrator','nickname':orra.nickname,'avatar':orra.avatar,'content':closing_text}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(meeting_stream(), media_type="text/event-stream")


# ──────────────────────────────────────────────
# Agent Sessions
# ──────────────────────────────────────────────
@app.get("/api/projects/{pid}/sessions")
async def get_sessions(pid: str, token=Depends(verify_token)):
    async with await get_db() as db:
        cur = await db.execute(
            "SELECT id, agent_name, created_at FROM sessions WHERE project_id=? AND role='agent' ORDER BY created_at",
            (pid,)
        )
        rows = await cur.fetchall()
    return [{"session_id":r[0],"agent":r[1],"created_at":r[2]} for r in rows]


# ──────────────────────────────────────────────
# Agent Profiles
# ──────────────────────────────────────────────
@app.get("/api/agents")
async def list_agents(token=Depends(verify_token)):
    return [
        {
            "name": p.name, "display_name": p.display_name, "nickname": p.nickname,
            "avatar": p.avatar, "accent": p.accent, "role": p.role,
            "personality": p.personality, "tone": p.tone, "scope": p.scope,
            "memory_focus": p.memory_focus, "output_contract": p.output_contract,
            "allowed_providers": list(p.allowed_providers),
        }
        for p in AGENT_PROFILES.values()
    ]


@app.get("/api/providers")
async def providers(token=Depends(verify_token)):
    return list_providers()


@app.get("/api/projects/{pid}/agents/{agent_name}/memory")
async def read_agent_memory(pid: str, agent_name: str, token=Depends(verify_token)):
    profile = get_profile(agent_name)
    memory = await get_agent_memory(pid, agent_name)
    return {
        "agent": profile.name, "display_name": profile.display_name,
        "nickname": profile.nickname, "avatar": profile.avatar,
        "accent": profile.accent, "role": profile.role,
        "scope": profile.scope, "memory": memory,
    }


# ──────────────────────────────────────────────
# Guest Agents
# ──────────────────────────────────────────────
class GuestAgentBody(BaseModel):
    name: str
    provider: str
    model: str | None = None
    role: str = ""
    prompt: str = ""
    parent_agent: str | None = None   # None = global guest; "literature" = Lumi's team
    api_key: str | None = None        # stored server-side only


@app.get("/api/guest-agents")
async def list_guest_agents(token=Depends(verify_token)):
    async with await get_db() as db:
        cur = await db.execute(
            "SELECT id,name,provider,model,role,prompt,parent_agent,enabled,created_at "
            "FROM guest_agents WHERE enabled=1 ORDER BY parent_agent NULLS LAST, created_at"
        )
        rows = await cur.fetchall()
    # api_key is never returned to the browser
    return [
        {
            "id": r[0], "name": r[1], "provider": r[2], "model": r[3],
            "role": r[4], "prompt": r[5], "parent_agent": r[6],
            "has_api_key": False,   # placeholder; real check below
            "enabled": bool(r[7]), "created_at": r[8],
        }
        for r in rows
    ]


@app.get("/api/agents/{agent_name}/team")
async def get_agent_team_endpoint(agent_name: str, token=Depends(verify_token)):
    """Return team members for a specific agent (no api_key)."""
    team = await get_agent_team(agent_name)
    return [
        {"id": m["id"], "name": m["name"], "provider": m["provider"],
         "model": m["model"], "role": m["role"], "has_key": bool(m.get("_api_key"))}
        for m in team
    ]


@app.post("/api/guest-agents")
async def create_guest_agent(body: GuestAgentBody, token=Depends(verify_token)):
    provider = body.provider.strip().lower()
    if provider not in {"openrouter", "gemini", "zai"}:
        raise HTTPException(400, f"Unsupported provider: {body.provider}")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name is required")
    parent = (body.parent_agent or "").strip().lower() or None
    from .agents.registry import AGENT_PROFILES
    if parent and parent not in AGENT_PROFILES:
        raise HTTPException(400, f"Unknown agent: {parent}")
    guest_id = str(uuid.uuid4())
    async with await get_db() as db:
        await db.execute(
            "INSERT INTO guest_agents (id,name,provider,model,role,prompt,parent_agent,api_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                guest_id, name[:80], provider,
                (body.model or "").strip()[:120],
                (body.role or "").strip()[:500],
                (body.prompt or "").strip()[:2000],
                parent,
                (body.api_key or "").strip() or None,
            ),
        )
        await db.commit()
    return {"id": guest_id, "parent_agent": parent}


@app.patch("/api/guest-agents/{guest_id}/key")
async def update_guest_api_key(guest_id: str, body: dict, token=Depends(verify_token)):
    """Update API key for a team member (key stored server-side only)."""
    key = (body.get("api_key") or "").strip() or None
    async with await get_db() as db:
        await db.execute(
            "UPDATE guest_agents SET api_key=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (key, guest_id),
        )
        await db.commit()
    return {"ok": True}


@app.delete("/api/guest-agents/{guest_id}")
async def disable_guest_agent(guest_id: str, token=Depends(verify_token)):
    async with await get_db() as db:
        await db.execute(
            "UPDATE guest_agents SET enabled=0, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (guest_id,),
        )
        await db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────
# Outputs
# ──────────────────────────────────────────────
class OutputsBody(BaseModel):
    title: str = ""
    topic: str = ""
    literature: str = ""
    research_question: str = ""
    study_design: str = ""
    stats: str = ""
    summary: str = ""
    writing: str = ""


@app.post("/api/projects/{pid}/outputs")
async def generate_outputs(pid: str, body: OutputsBody, token=Depends(verify_token)):
    import asyncio
    # Get project title/topic as fallback if not provided in body
    title = body.title
    topic = body.topic
    if not title:
        async with await get_db() as db:
            cur = await db.execute("SELECT title, topic FROM projects WHERE id=?", (pid,))
            row = await cur.fetchone()
        if row:
            title, topic = row[0] or "", row[1] or ""

    content = {
        "title": title, "topic": topic, "model_used": "claude-code",
        "literature":        body.literature,
        "research_question": body.research_question,
        "study_design":      body.study_design,
        "stats":             body.stats,
        "summary":           body.summary or body.writing,
    }

    # Run blocking file I/O in thread pool so it doesn't block the event loop
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: generate_proposal_docx(pid, content))
    await loop.run_in_executor(None, lambda: generate_literature_md(pid, content))
    await loop.run_in_executor(None, lambda: generate_analysis_py(pid, content))

    return {
        "files": ["proposal.docx", "literature.md", "analysis.py"]
    }


@app.get("/api/projects/{pid}/files/{filename}")
async def download_output(pid: str, filename: str, token=Depends(verify_token)):
    allowed = {"proposal.docx", "literature.md", "analysis.py", "progress.pptx"}
    if filename not in allowed:
        raise HTTPException(404, "File not found")
    path = Path(__file__).parent.parent / "outputs" / pid / filename
    if not path.exists():
        raise HTTPException(404, "File not generated yet")
    return FileResponse(str(path), filename=filename)


# ──────────────────────────────────────────────
# Frontend routes
# ──────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return (FRONTEND / "index.html").read_text()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(token=Depends(verify_token)):
    return (FRONTEND / "dashboard.html").read_text()

@app.get("/workspace/{pid}", response_class=HTMLResponse)
async def workspace(pid: str, token=Depends(verify_token)):
    return (FRONTEND / "workspace.html").read_text()
