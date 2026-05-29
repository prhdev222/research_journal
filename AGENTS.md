# research-assistant-cloudflare

Cloudflare Pages version of the AI Research Assistant for Dr. Uraree
(Hematology · Precision Medicine). This folder was copied from the original
FastAPI project and adapted for mobile-first Cloudflare deployment.

## Run

```bash
cd ~/prom4-oracle/research-assistant-cloudflare
npm install
npm run dev
```

Open the Wrangler local URL. For local AI calls, set `OPENAI_API_KEY` in
`.dev.vars`. Do not commit `.dev.vars`.

## Stack

- Cloudflare Pages static assets in `public/`
- Cloudflare Pages Functions in `functions/`
- OpenAI Responses API via `functions/api/ask.js`
- OpenRouter/OpenAI shared provider logic in `functions/_lib/ai.js`
- Optional compact Turso memory in `functions/_lib/turso.js`
- Browser `localStorage` for mobile notes/projects
- No frontend build step

## Codex Working Notes

- Treat copied `backend/` and `frontend/` as reference code from the original app.
- Cloudflare deployment uses `public/`, `functions/`, `package.json`, and `wrangler.toml`.
- Keep `OPENAI_API_KEY` server-side in Cloudflare secrets.
- Keep `OPENROUTER_API_KEY`, `TURSO_URL`, and `TURSO_AUTH_TOKEN` server-side.
- Agent meetings should use compact summaries, not full raw prompt history.
- Do not introduce a frontend build system unless explicitly requested.
- PDPA-first: be careful with patient data, de-identification, logs, exported files, and database contents.
- Explain WHY before HOW when making significant architecture or clinical-data decisions.
- After important fixes or discoveries, record learnings in the Oracle memory path below.

## App Modes

| # | Agent | File |
|---|-------|------|
| 1 | Literature | `functions/api/ask.js` |
| 2 | Research Question | `functions/api/ask.js` |
| 3 | Study Design | `functions/api/ask.js` |
| 4 | IRB/Ethics | `functions/api/ask.js` |
| 5 | Stats | `functions/api/ask.js` |
| 6 | Writing | `functions/api/ask.js` |
| 7 | De-ID | `functions/api/ask.js` |
| 8 | Summary | `functions/api/ask.js` |

## Oracle Memory

Session work should be recorded at:

```text
~/prom4-oracle/ψ/active/research-assistant.md
```

## Milestones

- [x] Copy original research-assistant reference project
- [x] Add Cloudflare Pages app shell
- [x] Add mobile-first UI
- [x] Keep AI key server-side in Pages Function
- [x] Add Research Journal / Journal Club modes
- [x] Add Professor Neo and Journal Club agents
- [x] Add compact agent meetings with optional Turso memory
- [ ] Deploy to Cloudflare Pages
- [ ] Add durable storage later if needed via D1 or KV
