"""
Agent 1: Literature Agent
— ใช้ WebSearch + WebFetch หา paper จริงจาก PubMed/DOI
— คืน link จริงพร้อม abstract
— เสริม Perplexity Deep Research ถ้ามี PERPLEXITY_API_KEY
"""
from ..models.claude_code_runner import run_with_session, AgentEvent
from ..utils.model_router import get_model
from ..utils.pubmed import search_pubmed, format_pubmed_seed
from ..models.perplexity_client import is_available as perplexity_available, search_papers as perplexity_search
from .registry import with_identity
from typing import AsyncGenerator

SYSTEM = """คุณคือ Literature Agent ผู้เชี่ยวชาญ Hematology และ Precision Medicine

หน้าที่: ค้นหา paper จริงจาก PubMed/Google Scholar แล้วสรุป gaps และ research questions

## วิธีทำงาน
1. ค้นหาด้วย WebSearch ("site:pubmed.ncbi.nlm.nih.gov [topic]" หรือ "[topic] hematology systematic review")
2. ดึง abstract ด้วย WebFetch จาก link ที่ได้
3. สรุปผล

## Output Format
### 📚 Papers Found
แต่ละ paper:
- **Title**: ...
- **Authors, Year, Journal**: ...
- **Link**: [PubMed URL หรือ DOI]
- **Key finding**: ...

### 🔍 Research Gaps
[gap ที่พบ]

### 💡 Suggested Research Questions
[3-5 คำถาม + PICO]

*AI-assisted via Claude Code | WebSearch enabled*"""

ALLOWED_TOOLS = ["WebSearch", "WebFetch"]


async def run_agent(
    topic: str,
    model_config: str | None = None,
    resume_session: str | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    model = get_model("literature", model_config)

    # PubMed seed
    try:
        papers = await search_pubmed(topic, limit=5)
        pubmed_seed = format_pubmed_seed(papers)
    except Exception as exc:
        pubmed_seed = f"PubMed seed search failed: {exc}"

    # Perplexity Deep Research (optional — only if API key present)
    perplexity_section = ""
    if perplexity_available():
        try:
            perplexity_text = await perplexity_search(topic)
            if perplexity_text:
                perplexity_section = (
                    "\n\n## Perplexity Deep Research Results\n"
                    "(Use these additional sources to enrich your analysis)\n\n"
                    + perplexity_text[:3000]
                )
        except Exception:
            pass  # Perplexity failure is non-fatal

    async for ev in run_with_session(
        (
            f"ค้นหา paper เกี่ยวกับ: {topic}\n\n"
            "Use these PubMed seed records first, then add interpretation and gaps.\n\n"
            f"{pubmed_seed}"
            f"{perplexity_section}\n\n"
            "กรุณาสรุปจาก paper จริงพร้อม link และแยก research gaps / suggested research questions."
        ),
        with_identity("literature", SYSTEM),
        model,
        allowed_tools=ALLOWED_TOOLS,
        resume_session=resume_session,
    ):
        yield ev
