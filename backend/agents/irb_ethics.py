"""Agent 4: IRB/Ethics Agent"""
from ..models.claude_code_runner import run_with_session, AgentEvent
from ..utils.model_router import get_model
from .registry import with_identity
from typing import AsyncGenerator

SYSTEM = """คุณคือ IRB/Ethics Agent บริบทไทย (สวรส./TCTR)
หน้าที่: ประเมิน ethical issues + IRB checklist + consent form

### IRB Checklist
Risk level · Vulnerable population · PDPA · Waiver of consent

### Ethical Issues

### Consent Form Draft (ภาษาไทย)

⚠️ ต้องผ่าน IRB จริงก่อน implement | *AI-assisted via Claude Code*"""

async def run_agent(study_design: str, model_config: str | None = None, resume_session: str | None = None) -> AsyncGenerator[AgentEvent, None]:
    model = get_model("irb_ethics", model_config)
    async for ev in run_with_session(f"Study Design:\n{study_design}", with_identity("irb_ethics", SYSTEM), model, resume_session=resume_session):
        yield ev
