export function hasTurso(env) {
  return Boolean(env.TURSO_URL);
}

export function getDb(env) {
  if (!env.TURSO_URL) return null;
  return {
    url: toHttpUrl(env.TURSO_URL),
    authToken: env.TURSO_AUTH_TOKEN || ""
  };
}

export async function ensureMemorySchema(db) {
  if (!db) return;
  const statements = [
    `CREATE TABLE IF NOT EXISTS projects (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      mode TEXT NOT NULL,
      topic TEXT,
      journal TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )`,
    `CREATE TABLE IF NOT EXISTS agent_memories (
      id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL,
      agent_name TEXT NOT NULL,
      memory_summary TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(project_id, agent_name)
    )`,
    `CREATE TABLE IF NOT EXISTS project_summaries (
      project_id TEXT PRIMARY KEY,
      summary TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )`,
    `CREATE TABLE IF NOT EXISTS meetings (
      id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL,
      title TEXT,
      created_at TEXT NOT NULL
    )`,
    `CREATE TABLE IF NOT EXISTS meeting_turns (
      id TEXT PRIMARY KEY,
      meeting_id TEXT NOT NULL,
      agent_name TEXT NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      created_at TEXT NOT NULL
    )`
  ];

  for (const sql of statements) {
    await execute(db, sql);
  }
}

async function execute(db, statement) {
  if (!db) return { rows: [] };
  const sql = typeof statement === "string" ? statement : statement.sql;
  const args = typeof statement === "string" ? [] : statement.args || [];
  const response = await fetch(`${db.url}/v2/pipeline`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${db.authToken}`
    },
    body: JSON.stringify({
      requests: [
        {
          type: "execute",
          stmt: {
            sql,
            args: args.map(toTursoArg)
          }
        },
        { type: "close" }
      ]
    })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.message || data.error || `Turso request failed (${response.status}).`);
  }
  return normalizeTursoResult(data);
}

function toHttpUrl(url) {
  return String(url || "").replace(/^libsql:\/\//, "https://").replace(/\/+$/, "");
}

function toTursoArg(value) {
  if (value === null || value === undefined) return { type: "null" };
  if (typeof value === "number" && Number.isInteger(value)) return { type: "integer", value: String(value) };
  if (typeof value === "number") return { type: "float", value };
  return { type: "text", value: String(value) };
}

function normalizeTursoResult(data) {
  const result = data.result || data.results?.[0]?.result || data.results?.[0]?.response?.result || data.results?.[0];
  const cols = result?.cols || [];
  const rows = (result?.rows || []).map((row) => {
    const values = Array.isArray(row) ? row : row.values || [];
    return Object.fromEntries(cols.map((col, index) => [col.name || col, fromTursoValue(values[index])]));
  });
  return { rows };
}

function fromTursoValue(value) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "object") return value;
  if (value.type === "null") return null;
  return value.value ?? value.base64 ?? null;
}

export async function upsertProject(db, project) {
  if (!db) return;
  const now = new Date().toISOString();
  await execute(db, {
    sql: `INSERT INTO projects (id, title, mode, topic, journal, created_at, updated_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        title = excluded.title,
        mode = excluded.mode,
        topic = excluded.topic,
        journal = excluded.journal,
        updated_at = excluded.updated_at`,
    args: [
      project.id,
      project.title || "Untitled research note",
      project.mode || "research",
      project.topic || "",
      project.journal || "generic",
      now,
      now
    ]
  });
}

export async function getProjectSummary(db, projectId) {
  if (!db) return "";
  const result = await execute(db, {
    sql: "SELECT summary FROM project_summaries WHERE project_id = ?",
    args: [projectId]
  });
  return String(result.rows?.[0]?.summary || "");
}

export async function getAgentMemories(db, projectId, agentNames) {
  if (!db || !agentNames.length) return {};
  const memories = {};
  for (const agentName of agentNames) {
    const result = await execute(db, {
      sql: "SELECT memory_summary FROM agent_memories WHERE project_id = ? AND agent_name = ?",
      args: [projectId, agentName]
    });
    memories[agentName] = String(result.rows?.[0]?.memory_summary || "");
  }
  return memories;
}

export async function createMeeting(db, projectId, title) {
  if (!db) return null;
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  await execute(db, {
    sql: "INSERT INTO meetings (id, project_id, title, created_at) VALUES (?, ?, ?, ?)",
    args: [id, projectId, title || "Agent meeting", now]
  });
  return id;
}

export async function saveMeetingTurn(db, meetingId, agentName, role, content) {
  if (!db || !meetingId || !content) return;
  await execute(db, {
    sql: "INSERT INTO meeting_turns (id, meeting_id, agent_name, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
    args: [crypto.randomUUID(), meetingId, agentName, role, content.slice(0, 5000), new Date().toISOString()]
  });
}

export async function upsertAgentMemory(db, projectId, agentName, memorySummary) {
  if (!db || !memorySummary) return;
  const now = new Date().toISOString();
  await execute(db, {
    sql: `INSERT INTO agent_memories (id, project_id, agent_name, memory_summary, updated_at)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(project_id, agent_name) DO UPDATE SET
        memory_summary = excluded.memory_summary,
        updated_at = excluded.updated_at`,
    args: [crypto.randomUUID(), projectId, agentName, memorySummary.slice(0, 900), now]
  });
}

export async function upsertProjectSummary(db, projectId, summary) {
  if (!db || !summary) return;
  const now = new Date().toISOString();
  await execute(db, {
    sql: `INSERT INTO project_summaries (project_id, summary, updated_at)
      VALUES (?, ?, ?)
      ON CONFLICT(project_id) DO UPDATE SET
        summary = excluded.summary,
        updated_at = excluded.updated_at`,
    args: [projectId, summary.slice(0, 1200), now]
  });
}
