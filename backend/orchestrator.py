"""
orchestrator.py — Claude Code Multi-Agent Pipeline

2 โหมด:
1. sequential_pipeline: รัน agent ทีละตัว ส่ง context ต่อกัน (default)
2. multi_agent_session: orchestrator ใช้ --agents spawn subagents คุยกันได้
"""
import json
from typing import AsyncGenerator
from .models.claude_code_runner import call, stream_events, AgentEvent
from .utils.model_router import get_model

# ── 9 Subagent definitions สำหรับ --agents flag ──────────────────────────────
AGENT_DEFINITIONS = {
    "literature": {
        "description": "ค้นหา paper จริงจาก PubMed + web วิเคราะห์ gaps เสนอ research questions",
        "prompt": "คุณคือ Literature Agent ผู้เชี่ยวชาญ Hematology ค้นหา paper จริงพร้อม link และวิเคราะห์ research gaps",
    },
    "research_question": {
        "description": "สร้าง research questions จาก gap analysis พร้อม feasibility assessment",
        "prompt": "คุณคือ Research Question Agent สร้าง PICO research questions พร้อมประเมิน feasibility",
    },
    "study_design": {
        "description": "เสนอ study design 3 แบบพร้อม pros/cons สำหรับ clinical research",
        "prompt": "คุณคือ Study Design Agent เสนอ design options สำหรับ Hematology research",
    },
    "irb_ethics": {
        "description": "ประเมิน IRB/Ethics checklist + consent form draft บริบทไทย",
        "prompt": "คุณคือ IRB/Ethics Agent ประเมิน ethics และสร้าง consent form ตามมาตรฐานไทย",
    },
    "stats": {
        "description": "วางแผน statistical analysis + generate Python/R code",
        "prompt": "คุณคือ Stats Agent วางแผน analysis และ generate code สำหรับ clinical research",
    },
    "writing": {
        "description": "เขียน draft manuscript IMRaD สำหรับ Hematology journals",
        "prompt": "คุณคือ Writing Agent เขียน academic medical writing สำหรับ Hematology journals",
    },
    "summary": {
        "description": "สรุป progress และ key outputs ของแต่ละ stage",
        "prompt": "คุณคือ Summary Agent สรุป research progress อย่างกระชับ",
    },
}

ORCHESTRATOR_SYSTEM = """คุณคือ Orchestrator หลักของระบบ AI Research Assistant
ผู้ใช้: แพทย์หญิงอุราลี — Hematology · Precision Medicine · Wellness & Anti-aging

คุณมี subagents ที่เรียกได้:
- literature: ค้นหา paper + web search
- research_question: สร้าง RQ + PICO
- study_design: ออกแบบ study 3 แบบ
- irb_ethics: IRB checklist + consent
- stats: analysis plan + Python/R code
- writing: draft manuscript IMRaD

วิธีทำงาน:
1. วิเคราะห์ topic + clinical context
2. เรียก subagents ตามลำดับที่เหมาะสม
3. ส่ง output ของแต่ละ agent ให้ agent ถัดไป
4. สรุปผลรวม

ตอบเป็น JSON เท่านั้น (ห้ามมี text นอก JSON):
{
  "research_type": "original_research",
  "topic_summary": "...",
  "clinical_context": "...",
  "agent_sequence": ["literature", "research_question", "study_design", "stats", "writing"],
  "notes": "..."
}

agent_sequence ต้องเป็น array ของ string ชื่อ agent เท่านั้น เลือกได้จาก: literature, research_question, study_design, irb_ethics, stats, writing, summary"""


async def plan(topic: str, model_config: str | None = None) -> dict:
    """Orchestrator วางแผน agent sequence"""
    model = get_model("orchestrator", model_config)
    result = await call(
        f"Research topic: {topic}\n\nวางแผน agent sequence + สรุป clinical context",
        ORCHESTRATOR_SYSTEM,
        model,
    )
    try:
        s = result.find("{")
        e = result.rfind("}") + 1
        return json.loads(result[s:e])
    except Exception:
        return {
            "research_type": "original_research",
            "topic_summary": topic,
            "clinical_context": result,
            "agent_sequence": ["literature", "research_question", "study_design", "stats", "writing"],
            "notes": "auto-planned",
        }


async def run_pipeline(
    topic: str,
    model_config: str | None = None,
    mode: str = "sequential",          # "sequential" | "multi_agent"
) -> AsyncGenerator[dict, None]:
    """
    Pipeline events (SSE):
    {"event":"plan", "data":{...}}
    {"event":"agent_start", "agent":"literature", "session_id":"..."}
    {"event":"chunk",       "agent":"literature", "data":"..."}
    {"event":"tool_use",    "agent":"literature", "tool":"WebSearch", "input":{...}}
    {"event":"agent_done",  "agent":"literature", "session_id":"..."}
    {"event":"done"}
    """
    from . import agents

    # ── Orchestrator Plan ────────────────────────────────────────────────────
    try:
        plan_result = await plan(topic, model_config)
    except Exception as exc:
        yield {
            "event": "error",
            "agent": "orchestrator",
            "data": str(exc),
        }
        return
    yield {"event": "plan", "data": plan_result}

    raw_seq = plan_result.get("agent_sequence",
        ["literature", "research_question", "study_design", "stats", "writing"])

    # Normalize: LLM sometimes returns objects instead of plain strings
    sequence = []
    for item in raw_seq:
        if isinstance(item, str):
            sequence.append(item)
        elif isinstance(item, dict):
            # e.g. {"agent": "literature", "angle": "..."} or {"name": "stats"}
            name = item.get("agent") or item.get("name") or ""
            if name:
                sequence.append(name)

    if not sequence:
        sequence = ["literature", "research_question", "study_design", "stats", "writing"]

    # Tell the frontend the full planned order so it can mark agents as queued
    yield {"event": "queue", "sequence": sequence}

    context = (
        f"Topic: {topic}\n"
        f"Research type: {plan_result.get('research_type', '')}\n"
        f"Clinical context: {plan_result.get('clinical_context', '')}"
    )

    agent_map = {
        "literature":        agents.literature.run_agent,
        "research_question": agents.research_question.run_agent,
        "study_design":      agents.study_design.run_agent,
        "irb_ethics":        agents.irb_ethics.run_agent,
        "stats":             agents.stats.run_agent,
        "writing":           agents.writing.run_agent,
        "summary":           agents.summary.run_agent,
    }

    agent_sessions: dict[str, str] = {}
    agent_results: dict[str, str] = {}

    # ── Run agents ──────────────────────────────────────────────────────────
    for i, agent_name in enumerate(sequence):
        fn = agent_map.get(agent_name)
        if fn is None:
            continue

        # Mark remaining agents still as queued
        remaining = [a for a in sequence[i+1:] if a in agent_map]
        if remaining:
            yield {"event": "queue", "sequence": remaining}

        agent_session_id = ""
        yield {"event": "agent_start", "agent": agent_name}
        output = ""
        had_error = False

        async for ev in fn(context, model_config):
            if ev.type == "chunk":
                yield {"event": "chunk", "agent": agent_name, "data": ev.data}
                output += ev.data
            elif ev.type == "tool_use":
                yield {
                    "event": "tool_use",
                    "agent": agent_name,
                    "tool": ev.tool_name,
                    "input": ev.tool_input,
                }
            elif ev.type == "done":
                agent_session_id = ev.session_id
            elif ev.type == "error":
                yield {
                    "event": "agent_error",   # non-fatal — shows in UI but continues
                    "agent": agent_name,
                    "data": ev.data,
                }
                had_error = True
                break

        agent_results[agent_name] = output
        agent_sessions[agent_name] = agent_session_id
        if output:
            context += f"\n\n=== {agent_name.upper()} OUTPUT ===\n{output}"

        yield {
            "event": "agent_done",
            "agent": agent_name,
            "content": output,
            "session_id": agent_session_id,
            "had_error": had_error,
        }

    yield {"event": "done", "results": agent_results, "sessions": agent_sessions}
