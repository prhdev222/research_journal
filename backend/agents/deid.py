"""Agent 7: De-ID Agent — PDPA compliance"""
from ..models.claude_code_runner import call
from ..utils.model_router import get_model
from .registry import with_identity

SYSTEM = """คุณคือ De-ID Agent
หน้าที่: ตัด/แทน PHI ทุกชิ้นออก

แทน: ชื่อ→[PATIENT_NAME] · HN→[ID] · วันเกิด→[DOB]
      ที่อยู่→[ADDRESS] · เบอร์→[PHONE] · แพทย์→[PROVIDER] · วันที่→[DATE]

Output: ข้อความ de-identified + รายการ PHI ที่พบ
⚠️ ประมวลผล local เท่านั้น | *AI-assisted via Claude Code*"""

async def run_agent(raw_text: str, model_config: str | None = None) -> str:
    model = get_model("deid", model_config)
    return await call(f"De-identify:\n\n{raw_text}", with_identity("deid", SYSTEM), model)
