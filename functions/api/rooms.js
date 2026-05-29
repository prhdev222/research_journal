import { clean, json } from "../_lib/http.js";
import { verifySession } from "../_lib/auth.js";
import {
  addRoomMessage,
  addRoomOutput,
  createJournalRoom,
  deleteJournalRoom,
  getDb,
  getJournalRoom,
  getRoomMessages,
  getRoomOutputs,
  hasTurso
} from "../_lib/turso.js";

export async function onRequestGet({ request, env }) {
  try {
    if (!hasTurso(env)) return json({ error: "Turso is required for shared rooms." }, 400);
    const url = new URL(request.url);
    const code = normalizeCode(url.searchParams.get("code"));
    if (!code) return json({ error: "Missing room code." }, 400);
    const db = getDb(env);
    const room = await getJournalRoom(db, code);
    if (!room) return json({ error: "Room not found." }, 404);
    return json({
      room,
      messages: await getRoomMessages(db, code),
      outputs: await getRoomOutputs(db, code)
    });
  } catch (error) {
    return json({ error: error.message || "Room sync failed." }, 500);
  }
}

export async function onRequestPost({ request, env }) {
  try {
    if (!hasTurso(env)) return json({ error: "Turso is required for shared rooms." }, 400);
    const body = await request.json();
    const action = clean(body.action, 30);
    const db = getDb(env);

    if (action === "create") {
      const session = await verifySession(env, request);
      if (session.role !== "admin" && session.role !== "disabled") {
        return json({ error: "Only admin can create rooms." }, 403);
      }
      const code = normalizeCode(body.code) || createRoomCode();
      const room = await createJournalRoom(db, {
        code,
        title: clean(body.title, 160) || "Journal Club Room",
        paperTitle: clean(body.paperTitle, 220),
        paperUrl: clean(body.paperUrl, 500),
        paperSummary: clean(body.paperSummary, 1600),
        createdBy: clean(body.author, 80) || "Admin"
      });
      await addRoomMessage(db, code, {
        author: clean(body.author, 80) || "Admin",
        kind: "system",
        content: `Room created: ${room.title}`
      });
      return json({
        room,
        messages: await getRoomMessages(db, code),
        outputs: await getRoomOutputs(db, code)
      });
    }

    if (action === "join") {
      const code = normalizeCode(body.code);
      if (!code) return json({ error: "Missing room code." }, 400);
      const room = await getJournalRoom(db, code);
      if (!room) return json({ error: "Room not found." }, 404);
      return json({
        room,
        messages: await getRoomMessages(db, code),
        outputs: await getRoomOutputs(db, code)
      });
    }

    if (action === "message") {
      const code = normalizeCode(body.code);
      if (!code) return json({ error: "Missing room code." }, 400);
      const room = await getJournalRoom(db, code);
      if (!room) return json({ error: "Room not found." }, 404);
      await addRoomMessage(db, code, {
        author: clean(body.author, 80) || "Member",
        kind: clean(body.kind, 30) || "comment",
        content: clean(body.content, 1200)
      });
      return json({
        room,
        messages: await getRoomMessages(db, code),
        outputs: await getRoomOutputs(db, code)
      });
    }

    if (action === "output") {
      const code = normalizeCode(body.code);
      if (!code) return json({ error: "Missing room code." }, 400);
      const room = await getJournalRoom(db, code);
      if (!room) return json({ error: "Room not found." }, 404);
      await addRoomOutput(db, code, {
        label: clean(body.label, 80) || "AI Meeting",
        content: clean(body.content, 5000)
      });
      return json({
        room,
        messages: await getRoomMessages(db, code),
        outputs: await getRoomOutputs(db, code)
      });
    }

    if (action === "delete") {
      const session = await verifySession(env, request);
      if (session.role !== "admin" && session.role !== "disabled") {
        return json({ error: "Only admin can delete rooms." }, 403);
      }
      const code = normalizeCode(body.code);
      if (!code) return json({ error: "Missing room code." }, 400);
      await deleteJournalRoom(db, code);
      return json({ ok: true, code });
    }

    return json({ error: "Unknown room action." }, 400);
  } catch (error) {
    return json({ error: error.message || "Room action failed." }, 500);
  }
}

function normalizeCode(value) {
  return clean(value, 24).toUpperCase().replace(/[^A-Z0-9-]/g, "").slice(0, 16);
}

function createRoomCode() {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => alphabet[byte % alphabet.length]).join("");
}
