# research-assistant

AI Research Assistant สำหรับ แพทย์หญิงอุราลี (Hematology · Precision Medicine)

## Run

```bash
cd ~/projects/research-assistant
python -m uvicorn backend.main:app --reload --port 8000
```

เปิด http://localhost:8000 — password เริ่มต้น: `research`

## Stack

- FastAPI + Uvicorn (Python)
- HTML/JS + TailwindCSS (no build step)
- SQLite → `research_assistant.db`
- Claude Opus 4 (orchestrator) + Claude Sonnet 4 (9 sub-agents)

## Sub-Agents (9 ตัว)

| # | Agent | File |
|---|-------|------|
| 1 | Literature | `backend/agents/literature.py` |
| 2 | Research Question | `backend/agents/research_question.py` |
| 3 | Study Design | `backend/agents/study_design.py` |
| 4 | IRB/Ethics | `backend/agents/irb_ethics.py` |
| 5 | Stats | `backend/agents/stats.py` |
| 6 | Writing | `backend/agents/writing.py` |
| 7 | De-ID | `backend/agents/deid.py` |
| 8 | Summary | `backend/agents/summary.py` |
| 9 | Output | `backend/agents/output.py` |

## Oracle Memory (maw)

งาน session ทั้งหมดบันทึกที่ `~/prom4-oracle/ψ/active/research-assistant.md`

## Milestones

- [x] Week 1: Scaffold + Auth + Chat UI + SQLite + model_router
- [ ] Week 2: Claude clients + Literature Agent + PubMed API
- [ ] Week 3: Research Q Agent + Study Design Agent
- [ ] Week 4: Stats Agent + Writing Agent
- [ ] Week 5: Output Generator (.docx · .md · .py) + Model Selector UI
- [ ] Week 6+: Perplexity · IRB · De-ID · pptx
