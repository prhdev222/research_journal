"""
Agent 9: Output Agent
Input: all drafts
Output: proposal.docx, manuscript.docx, progress.pptx, analysis.py
ใช้ python-docx + python-pptx — ไม่ใช้ LLM
"""
import os
from pathlib import Path
from docx import Document
from pptx import Presentation
from pptx.util import Inches, Pt

OUTPUTS_DIR = Path(__file__).parent.parent.parent / "outputs"

def _ensure_output_dir(project_id: str) -> Path:
    d = OUTPUTS_DIR / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def generate_proposal_docx(project_id: str, content: dict) -> str:
    """สร้าง proposal.docx จาก content dict"""
    out_dir = _ensure_output_dir(project_id)
    doc = Document()
    doc.add_heading("Research Proposal", 0)
    doc.add_paragraph(f"AI-assisted | Model: {content.get('model_used', 'claude')}")
    doc.add_heading("Title", 1)
    doc.add_paragraph(content.get("title", ""))
    doc.add_heading("Background & Literature", 1)
    doc.add_paragraph(content.get("literature", ""))
    doc.add_heading("Research Question", 1)
    doc.add_paragraph(content.get("research_question", ""))
    doc.add_heading("Study Design", 1)
    doc.add_paragraph(content.get("study_design", ""))
    doc.add_heading("Statistical Analysis", 1)
    doc.add_paragraph(content.get("stats", ""))
    path = out_dir / "proposal.docx"
    doc.save(str(path))
    return str(path)

def generate_literature_md(project_id: str, content: dict) -> str:
    out_dir = _ensure_output_dir(project_id)
    path = out_dir / "literature.md"
    text = "\n\n".join(
        [
            f"# Literature Summary: {content.get('title', 'Research Project')}",
            content.get("literature", "").strip() or "_No literature output yet._",
            "## Research Questions",
            content.get("research_question", "").strip() or "_No research question output yet._",
            "\n_AI-assisted via Claude Code. Verify citations before use._",
        ]
    )
    path.write_text(text, encoding="utf-8")
    return str(path)

def generate_analysis_py(project_id: str, content: dict) -> str:
    out_dir = _ensure_output_dir(project_id)
    path = out_dir / "analysis.py"
    stats = content.get("stats", "").strip()
    if not stats:
        stats = "No stats plan has been generated yet."
    text = f'''"""
Analysis scaffold for: {content.get("title", "Research Project")}

AI-assisted via Claude Code. Review before running on real data.
"""

# Original Stats Agent output:
STATS_PLAN = r"""{stats}"""

def main():
    print("Review STATS_PLAN, then replace this scaffold with the approved analysis code.")

if __name__ == "__main__":
    main()
'''
    path.write_text(text, encoding="utf-8")
    return str(path)

def generate_pptx(project_id: str, content: dict) -> str:
    """สร้าง progress.pptx"""
    out_dir = _ensure_output_dir(project_id)
    prs = Presentation()
    slide_layout = prs.slide_layouts[1]
    # Title slide
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = content.get("title", "Research Progress")
    slide.placeholders[1].text = "AI-assisted (claude-sonnet-4-5)"
    # Summary slide
    slide2 = prs.slides.add_slide(slide_layout)
    slide2.shapes.title.text = "Progress"
    slide2.placeholders[1].text = content.get("summary", "")
    path = out_dir / "progress.pptx"
    prs.save(str(path))
    return str(path)
