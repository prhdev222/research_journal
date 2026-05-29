import { createClient } from "@libsql/client/web";

export function hasTurso(env) {
  return Boolean(env.TURSO_URL);
}

export function getDb(env) {
  if (!env.TURSO_URL) return null;
  return createClient({
    url: env.TURSO_URL,
    authToken: env.TURSO_AUTH_TOKEN || undefined
  });
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
    await db.execute(sql);
  }
}

export async function upsertProject(db, project) {
  if (!db) return;
  const now = new Date().toISOString();
  await db.execute({
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
  const result = await db.execute({
    sql: "SELECT summary FROM project_summaries WHERE project_id = ?",
    args: [projectId]
  });
  return String(result.rows?.[0]?.summary || "");
}

export async function getAgentMemories(db, projectId, agentNames) {
  if (!db || !agentNames.length) return {};
  const memories = {};
  for (const agentName of agentNames) {
    const result = await db.execute({
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
  await db.execute({
    sql: "INSERT INTO meetings (id, project_id, title, created_at) VALUES (?, ?, ?, ?)",
    args: [id, projectId, title || "Agent meeting", now]
  });
  return id;
}

export async function saveMeetingTurn(db, meetingId, agentName, role, content) {
  if (!db || !meetingId || !content) return;
  await db.execute({
    sql: "INSERT INTO meeting_turns (id, meeting_id, agent_name, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
    args: [crypto.randomUUID(), meetingId, agentName, role, content.slice(0, 5000), new Date().toISOString()]
  });
}

export async function upsertAgentMemory(db, projectId, agentName, memorySummary) {
  if (!db || !memorySummary) return;
  const now = new Date().toISOString();
  await db.execute({
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
  await db.execute({
    sql: `INSERT INTO project_summaries (project_id, summary, updated_at)
      VALUES (?, ?, ?)
      ON CONFLICT(project_id) DO UPDATE SET
        summary = excluded.summary,
        updated_at = excluded.updated_at`,
    args: [projectId, summary.slice(0, 1200), now]
  });
}
