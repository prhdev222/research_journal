"""Agent 2: Research Question Agent — เสริม Perplexity ถ้ามี key"""
from ..models.claude_code_runner import run_with_session, AgentEvent
from ..utils.model_router import get_model
from ..models.perplexity_client import is_available as perplexity_available, search_papers as perplexity_search
from .registry import with_identity
from typing import AsyncGenerator
import re

SYSTEM = """คุณคือ Research Question Agent
หน้าที่: สร้าง research questions จาก gap analysis พร้อม feasibility

### Research Questions
แต่ละ RQ: คำถาม · PICO · Feasibility [สูง/กลาง/ต่ำ] · Impact

### Recommended RQ
[RQ ที่แนะนำ + เหตุผล]

*AI-assisted via Claude Code*"""


def _extract_topic(context: str) -> str:
    """Pull short topic string from pipeline context for Perplexity query."""
    m = re.search(r"Topic:\s*(.+)", context)
    return m.group(1).strip()[:200] if m else context[:200]


async def run_agent(gap_analysis: str, model_config: str | None = None, resume_session: str | None = None) -> AsyncGenerator[AgentEvent, None]:
    model = get_model("research_question", model_config)

    perplexity_section = ""
    if perplexity_available():
        try:
            topic = _extract_topic(gap_analysis)
            perplexity_text = await perplexity_search(
                f"Recent research questions and knowledge gaps in: {topic}"
            )
            if perplexity_text:
                perplexity_section = (
                    "\n\n## Perplexity: Related Research Directions\n"
                    + perplexity_text[:2000]
                )
        except Exception:
            pass

    prompt = f"Gap Analysis:\n{gap_analysis}{perplexity_section}"
    async for ev in run_with_session(prompt, with_identity("research_question", SYSTEM), model, resume_session=resume_session):
        yield ev
