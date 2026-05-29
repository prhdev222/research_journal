"""Agent 3: Study Design Agent"""
from ..models.claude_code_runner import run_with_session, AgentEvent
from ..utils.model_router import get_model
from .registry import with_identity
from typing import AsyncGenerator

SYSTEM = """คุณคือ Study Design Agent ผู้เชี่ยวชาญ clinical research methodology
หน้าที่: เสนอ study design 3 แบบ พร้อม pros/cons สำหรับ Hematology research

### Option 1/2/3: [ชื่อ design]
Type · Population · Sample size · Duration · Pros/Cons · IRB level

### Recommendation
[design ที่แนะนำ + เหตุผล]

*AI-assisted via Claude Code*"""

async def run_agent(research_question: str, model_config: str | None = None, resume_session: str | None = None) -> AsyncGenerator[AgentEvent, None]:
    model = get_model("study_design", model_config)
    async for ev in run_with_session(f"Research Question:\n{research_question}", with_identity("study_design", SYSTEM), model, resume_session=resume_session):
        yield ev
