import aiosqlite
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "../../research_assistant.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  topic TEXT,
  status TEXT DEFAULT 'draft',
  model_config TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id),
  role TEXT,
  agent_name TEXT,
  model_used TEXT,
  content TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_cache (
  pmid TEXT PRIMARY KEY,
  title TEXT, abstract TEXT,
  authors TEXT, journal TEXT, year INTEGER,
  source TEXT,
  fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drafts (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id),
  type TEXT,
  version INTEGER DEFAULT 1,
  content TEXT, file_path TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_memories (
  project_id TEXT REFERENCES projects(id),
  agent_name TEXT NOT NULL,
  memory TEXT,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (project_id, agent_name)
);

CREATE TABLE IF NOT EXISTS meetings (
  id TEXT PRIMARY KEY,
  project_id TEXT REFERENCES projects(id),
  question TEXT NOT NULL,
  agent_names TEXT,
  status TEXT DEFAULT 'running',
  summary TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meeting_turns (
  id TEXT PRIMARY KEY,
  meeting_id TEXT REFERENCES meetings(id),
  round INTEGER,
  agent_name TEXT,
  content TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guest_agents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT,
  role TEXT,
  prompt TEXT,
  parent_agent TEXT,   -- NULL = global guest | "literature" = Lumi's team, etc.
  api_key TEXT,        -- stored locally; never sent to browser in plaintext
  enabled INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

# Migrations: add new columns to existing tables safely
_MIGRATIONS = [
    "ALTER TABLE guest_agents ADD COLUMN parent_agent TEXT",
    "ALTER TABLE guest_agents ADD COLUMN api_key TEXT",
]

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
        # Run migrations (ignore errors = column already exists)
        for sql in _MIGRATIONS:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass

async def get_db():
    return aiosqlite.connect(DB_PATH)
