"""Agent 6: Writing Agent — IMRaD draft + Journal Formatter"""
from ..models.claude_code_runner import run_with_session, AgentEvent
from ..utils.model_router import get_model
from .registry import with_identity
from typing import AsyncGenerator

# ── Journal format specs ──────────────────────────────────────────────────────
JOURNAL_FORMATS: dict[str, dict] = {
    "blood": {
        "name": "Blood (ASH)",
        "word_limit": 4000,
        "abstract": "structured (Background · Methods · Results · Conclusions, ≤250 words)",
        "sections": "Introduction · Methods · Results · Discussion · Conclusions",
        "style": "American English · active voice preferred · Vancouver citation style",
        "notes": "Key points box (3-5 bullets) required. Supplement allowed.",
    },
    "bjh": {
        "name": "British Journal of Haematology (BJH)",
        "word_limit": 3500,
        "abstract": "unstructured (≤250 words)",
        "sections": "Introduction · Materials and Methods · Results · Discussion",
        "style": "British English spelling · passive voice acceptable · Vancouver citations",
        "notes": "No 'Conclusions' heading — end Discussion with conclusion paragraph.",
    },
    "haematologica": {
        "name": "Haematologica (EHA)",
        "word_limit": 4500,
        "abstract": "structured (Background · Design and Methods · Results · Interpretation, ≤250 words)",
        "sections": "Introduction · Design and Methods · Results · Discussion",
        "style": "American English · concise · Vancouver citations",
        "notes": "Graphical abstract encouraged. Supplemental data common.",
    },
    "annals": {
        "name": "Annals of Hematology (Springer)",
        "word_limit": 4000,
        "abstract": "structured (Purpose · Methods · Results · Conclusion, ≤250 words)",
        "sections": "Introduction · Materials and Methods · Results · Discussion · Conclusion",
        "style": "American English · Springer Vancouver style",
        "notes": "Separate Conclusion section required. Online supplementary allowed.",
    },
}

BASE_SYSTEM = """คุณคือ Writing Agent ผู้เชี่ยวชาญ medical writing สำหรับ Hematology journals
Style: Academic English · concise · evidence-based
Citation placeholder: [Author, Year] — ตรวจสอบก่อน submit เสมอ

*AI-assisted draft via Claude Code — requires human review before submission*"""


def _build_system(journal_target: str | None) -> str:
    if not journal_target:
        return BASE_SYSTEM + "\nTarget: Blood · BJH · Haematologica · Annals of Hematology (generic format)"
    key = journal_target.lower().strip()
    fmt = JOURNAL_FORMATS.get(key)
    if not fmt:
        return BASE_SYSTEM + f"\nTarget journal: {journal_target}"
    return (
        BASE_SYSTEM
        + f"\n\n## Target Journal: {fmt['name']}\n"
        + f"- Word limit (main text): ~{fmt['word_limit']} words\n"
        + f"- Abstract: {fmt['abstract']}\n"
        + f"- Sections: {fmt['sections']}\n"
        + f"- Style: {fmt['style']}\n"
        + f"- Notes: {fmt['notes']}\n\n"
        + "Follow this journal's requirements strictly. "
        + "Mark each section heading exactly as specified above."
    )


def _get_journal(journal_target: str | None, model_config: str | None) -> str | None:
    """Resolve journal: explicit param > model_config JSON > None."""
    if journal_target:
        return journal_target
    if model_config:
        try:
            import json
            cfg = json.loads(model_config)
            return cfg.get("writing_journal")
        except Exception:
            pass
    return None


async def run_agent(
    context: str,
    section: str = "introduction_methods",
    journal_target: str | None = None,
    model_config: str | None = None,
    resume_session: str | None = None,
) -> AsyncGenerator[AgentEvent, None]:
    model = get_model("writing", model_config)
    resolved_journal = _get_journal(journal_target, model_config)
    system = _build_system(resolved_journal)
    key = resolved_journal.lower() if resolved_journal else None
    journal_note = f" [{JOURNAL_FORMATS[key]['name']}]" if key and key in JOURNAL_FORMATS else ""
    prompt = f"Section: {section}{journal_note}\n\nContext:\n{context}"
    async for ev in run_with_session(prompt, with_identity("writing", system), model, resume_session=resume_session):
        yield ev
