"""Agent 5: Stats Agent"""
from ..models.claude_code_runner import run_with_session, AgentEvent
from ..utils.model_router import get_model
from .registry import with_identity
from typing import AsyncGenerator

SYSTEM = """คุณคือ Stats Agent ผู้เชี่ยวชาญ biostatistics + clinical research
หน้าที่: วางแผน statistical analysis + generate Python/R code

### Analysis Plan
Primary outcome · Statistical test · Sample size · Missing data strategy

### Python Code
```python
# analysis.py — AI-assisted via Claude Code
...
```

### R Code (alternative)

⚠️ ตรวจสอบ code ก่อน run จริง | *AI-assisted via Claude Code*"""

async def run_agent(design_and_variables: str, model_config: str | None = None, resume_session: str | None = None) -> AsyncGenerator[AgentEvent, None]:
    model = get_model("stats", model_config)
    async for ev in run_with_session(f"Design & Variables:\n{design_and_variables}", with_identity("stats", SYSTEM), model, resume_session=resume_session):
        yield ev
