from . import (
    literature, research_question, study_design,
    irb_ethics, stats, writing, deid, summary, output,
)

# Export SYSTEM prompts สำหรับ chat endpoint
from .literature import SYSTEM as LITERATURE_SYSTEM, ALLOWED_TOOLS as LITERATURE_TOOLS
from .research_question import SYSTEM as RESEARCH_Q_SYSTEM
from .study_design import SYSTEM as STUDY_DESIGN_SYSTEM
from .irb_ethics import SYSTEM as IRB_SYSTEM
from .stats import SYSTEM as STATS_SYSTEM
from .writing import SYSTEM as WRITING_SYSTEM
from .summary import SYSTEM as SUMMARY_SYSTEM
