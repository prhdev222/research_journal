"""
model_router.py — เลือก model ต่อ agent
ใช้ชื่อ model ที่ claude CLI รองรับ
"""
import json
from typing import Literal

AgentName = Literal[
    "orchestrator", "literature", "research_question",
    "study_design", "irb_ethics", "stats", "writing",
    "deid", "summary", "output",
]

# Claude Code CLI model names
OPUS   = "claude-opus-4-5"
SONNET = "claude-sonnet-4-6"  # latest sonnet

DEFAULT_MODEL_CONFIG: dict[str, str] = {
    "orchestrator":      OPUS,
    "literature":        SONNET,
    "research_question": SONNET,
    "study_design":      SONNET,
    "irb_ethics":        SONNET,
    "stats":             SONNET,
    "writing":           SONNET,
    "deid":              SONNET,
    "summary":           SONNET,
    "output":            SONNET,  # python-docx ไม่ใช้ LLM จริง
}

PROVIDER_REGISTRY: dict[str, dict[str, str]] = {
    "claude-code": {
        "status": "active",
        "env_key": "",
        "description": "Claude Code CLI — default provider for all agents.",
    },
    "pubmed": {
        "status": "active-tool",
        "env_key": "",
        "description": "NCBI PubMed E-utilities seed search for Literature Agent.",
    },
    "openrouter": {
        "status": "api-configurable",
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "description": "OpenAI-compatible gateway for multiple models and vendors.",
    },
    "gemini": {
        "status": "api-configurable",
        "env_key": "GEMINI_API_KEY",
        "description": "Google Gemini API provider for long-context and synthesis tasks.",
    },
    "zai": {
        "status": "api-configurable",
        "env_key": "ZAI_API_KEY",
        "description": "Z.ai / GLM provider. Use OpenAI-compatible mode when available.",
    },
    "local-python": {
        "status": "active-tool",
        "env_key": "",
        "description": "Local artifact generation using Python libraries.",
    },
}

import os as _os

def list_providers() -> dict[str, dict[str, str]]:
    providers = {}
    for key, config in PROVIDER_REGISTRY.items():
        env_key = config.get("env_key", "")
        public = {k: v for k, v in config.items() if k != "env_key"}
        public["env_key"] = env_key
        public["configured"] = True if not env_key else bool(_os.getenv(env_key))
        providers[key] = public
    return providers

def get_model(agent: str, project_config: str | None = None) -> str:
    if project_config:
        try:
            cfg = json.loads(project_config)
            if agent in cfg:
                return cfg[agent]
        except Exception:
            pass
    return DEFAULT_MODEL_CONFIG.get(agent, SONNET)
