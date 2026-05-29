# JEDA Research Assistant for Cloudflare Pages

Mobile-first Cloudflare Pages version of the existing Research Assistant.

## What Deploys

Cloudflare Pages serves:

- `public/index.html` - mobile-first research assistant UI
- `functions/api/ask.js` - server-side AI API route

The copied `backend/` and `frontend/` folders are kept as reference from the original FastAPI version. They are not used by Cloudflare Pages deployment.

## Security

- Do not put `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or any provider key in browser JavaScript.
- Set provider keys as Cloudflare Pages secrets.
- Keep patient identifiers out of prompts and local notes.
- This app stores projects and history in browser `localStorage`, not a server database.

## Token Saving

The UI defaults to `Short` response mode. The Pages Function enforces smaller
input context and `max_output_tokens` by mode:

- `Short` - best summary, maximum 5 bullets
- `Normal` - compact structured note
- `Deep` - fuller research note when needed

Agent meetings are also capped:

- each selected agent gets a compact prompt and short answer budget
- Professor Neo synthesizes the final answer
- Turso memory stores compact summaries, not full prompts
- memory updates use deterministic compaction, not extra AI calls

## Journal Club

The first screen has two modes with different agent rosters:

- `Research Journal` - research question, protocol, stats, writing, de-ID, and summary agents.
- `Journal Club` - paper appraisal agents, including `Professor Neo` for expert opinion.

The Journal Club mode includes a paper intake panel:

- Paste a paper link and use `Read link` to extract readable page text.
- Upload a PDF/text file to extract paper text locally in the browser.
- Use `Analyze paper` to send a structured journal-club prompt through `/api/ask`.

PDF extraction uses browser-side PDF.js, so uploaded PDF contents are not sent
anywhere until the user taps `Analyze paper`.

Professor Neo is a senior professor-style expert opinion agent for journal
analysis, research critique, reviewer-style questions, and practical next steps.

Use the `Thai` button beside the result to translate the current answer into
professional Thai through the server-side OpenRouter route. The translator keeps
headings, bullets, statistics, abbreviations, and citations.
Long outputs are split into chunks so meeting results translate fully.

Optional translation model override:

```bash
OPENROUTER_MODEL_TRANSLATE=google/gemini-2.5-flash-lite
```

## Agent Meetings And Turso Memory

Use `Meet Agents` to ask 2-4 mode-specific agents to answer briefly. Professor
Neo automatically gives the final synthesis.

`Active Meeting` is optional and off by default. When enabled:

- the meeting creates one high-value follow-up question
- Professor Fisher and Professor Neo answer that follow-up
- extra guests can be invited afterward: Watson, Chen, Mimi, Osler, or Perplexity
- the flow reuses compact meeting context to limit token use

Turso is optional in local dev. Without `TURSO_URL`, meetings still work but
memory is local-only. With Turso configured, the app stores:

- compact project summary
- compact per-agent memory
- meeting transcript turns

Create local `.dev.vars` for Turso:

```bash
TURSO_URL=http://127.0.0.1:8080
TURSO_AUTH_TOKEN=
```

For deployed Cloudflare Pages:

```bash
npx wrangler pages secret put TURSO_URL --project-name research-assistant-cloudflare
npx wrangler pages secret put TURSO_AUTH_TOKEN --project-name research-assistant-cloudflare
```

Schema reference is in `migrations/turso-memory.sql`. The Functions also create
tables automatically on first meeting request when Turso is configured.

## Local Dev

Install dependencies:

```bash
npm install
```

Run Cloudflare Pages locally:

```bash
npm run dev
```

For local AI calls, create `.dev.vars`:

```bash
OPENROUTER_API_KEY=your_openrouter_key_here
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_MODEL_TRANSLATE=google/gemini-2.5-flash-lite
```

If `OPENROUTER_API_KEY` exists, the app uses OpenRouter. If it is missing, the
Function falls back to OpenAI with `OPENAI_API_KEY`.

Optional per-agent OpenRouter model overrides:

```bash
OPENROUTER_MODEL_LITERATURE=google/gemini-2.5-flash-lite
OPENROUTER_MODEL_QUESTION=google/gemini-2.5-flash-lite
OPENROUTER_MODEL_DESIGN=google/gemini-2.5-flash
OPENROUTER_MODEL_ETHICS=google/gemini-2.5-flash-lite
OPENROUTER_MODEL_STATS=google/gemini-2.5-flash
OPENROUTER_MODEL_WRITING=google/gemini-2.5-flash
OPENROUTER_MODEL_DEID=google/gemini-2.5-flash-lite
OPENROUTER_MODEL_SUMMARY=google/gemini-2.5-flash-lite
OPENROUTER_MODEL_JOURNALCLUB=google/gemini-2.5-flash
OPENROUTER_MODEL_METHODS=google/gemini-2.5-flash
OPENROUTER_MODEL_CLINICAL=google/gemini-2.5-flash-lite
OPENROUTER_MODEL_NEO=anthropic/claude-sonnet-4.6
OPENROUTER_MODEL_PERPLEXITY=perplexity/sonar
OPENROUTER_MODEL_WATSON=openai/gpt-5
OPENROUTER_MODEL_CHEN=deepseek/deepseek-v3.2
OPENROUTER_MODEL_MIMI=deepseek/deepseek-r1
OPENROUTER_MODEL_OSLER=anthropic/claude-opus-4.5
OPENROUTER_MODEL_FISHER=google/gemini-2.5-flash
```

Cost-conscious default routing:

- Cheap/default: `google/gemini-2.5-flash-lite`
- Better analysis: `google/gemini-2.5-flash`
- Expert synthesis only: `anthropic/claude-sonnet-4.6` for Professor Neo
- In Research mode, Professor Neo can be invited as a meeting guest when higher-quality Claude review is worth the cost.
- Guest search: `perplexity/sonar` for Perplexity Search
- Guest GPT-5 expert: `openai/gpt-5` for Professor Watson
- Guest DeepSeek strategist: `deepseek/deepseek-v3.2` for Professor Chen
- Guest hard reasoning: `deepseek/deepseek-r1` for Professor Mimi
- Premium important-decision review only: `anthropic/claude-opus-4.5` for Professor Osler
- Research final synthesis: `google/gemini-2.5-flash` for Professor Fisher
- Thai translation: `google/gemini-2.5-flash-lite`

Agent cards show model and character in the UI without spending tokens. The
backend sends only one short `Voice:` line per agent so meetings keep token use
low.

Do not commit `.dev.vars`.

Restart `npm run dev` after changing `.dev.vars`. Wrangler only loads local
secrets when the dev server starts.

## Cloudflare Setup

Create the Pages project from this folder, then set:

```bash
npx wrangler pages secret put OPENROUTER_API_KEY --project-name research-assistant-cloudflare
```

Optional model override:

```bash
npx wrangler pages secret put OPENROUTER_MODEL --project-name research-assistant-cloudflare
```

Deploy:

```bash
npm run deploy
```

## Notes

The AI endpoint uses OpenRouter first when `OPENROUTER_API_KEY` is configured.
OpenAI remains available as fallback through `OPENAI_API_KEY`.
