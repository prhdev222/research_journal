"""Agent 8: Summary Agent"""
from ..models.claude_code_runner import run_with_session, AgentEvent
from ..utils.model_router import get_model
from .registry import with_identity
from typing import AsyncGenerator

SYSTEM = """คุณคือ Summary Agent
หน้าที่: สรุป progress ของ research project แต่ละ stage

### Progress Summary
Stage · Status · Key outputs · Next steps

### Paper Summary (ถ้ามี)
Title draft · Research question · Design · Key finding

*AI-assisted via Claude Code*"""

async def run_agent(stage_content: str, model_config: str | None = None, resume_session: str | None = None) -> AsyncGenerator[AgentEvent, None]:
    model = get_model("summary", model_config)
    async for ev in run_with_session(f"Stage content:\n{stage_content}", with_identity("summary", SYSTEM), model, resume_session=resume_session):
        yield ev
