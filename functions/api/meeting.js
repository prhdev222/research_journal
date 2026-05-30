import { AGENTS, RESPONSE_MODES, buildInstructions, callModel } from "../_lib/ai.js";
import { clean, json } from "../_lib/http.js";
import {
  createMeeting,
  ensureMemorySchema,
  getAgentMemories,
  getDb,
  getProjectSummary,
  hasTurso,
  saveMeetingTurn,
  upsertAgentMemory,
  upsertProject,
  upsertProjectSummary
} from "../_lib/turso.js";

const MEETING_AGENT_LIMIT = 4;
const AGENT_TOKENS = 820;
const NEO_TOKENS = 1300;
const FOLLOWUP_TOKENS = 720;

export async function onRequestPost({ request, env }) {
  try {
    const body = await request.json();
    const project = normalizeProject(body.project || {});
    const modeId = RESPONSE_MODES[body.mode] ? body.mode : "short";
    const mode = RESPONSE_MODES[modeId];
    const selectedAgents = normalizeAgents(body.agents, project.mode);
    const question = clean(body.question, 1400);
    const paperText = clean(body.paperText || project.paperText, project.mode === "journal" ? 6500 : 1200);
    const activeMeeting = Boolean(body.activeMeeting);
    const customPrompts = normalizeCustomPrompts(body.customPrompts);

    if (!question && !project.topic && !paperText) {
      return json({ error: "Please provide a meeting question, topic, or paper text." }, 400);
    }

    const db = getDb(env);
    const memoryEnabled = hasTurso(env);
    let memoryAvailable = false;
    let memoryWarning = "";
    let projectSummary = "";
    let agentMemories = {};
    let meetingId = null;

    if (memoryEnabled) {
      try {
        await ensureMemorySchema(db);
        await upsertProject(db, project);
        projectSummary = await getProjectSummary(db, project.id);
      agentMemories = await getAgentMemories(db, project.id, [...selectedAgents, finalSynthesizer(project.mode)]);
        meetingId = await createMeeting(db, project.id, question.slice(0, 120) || "Agent meeting");
        await saveMeetingTurn(db, meetingId, "user", "user", question || project.topic || "Meeting started.");
        memoryAvailable = true;
      } catch (error) {
        memoryWarning = `Turso memory unavailable: ${error.message || "connection failed"}`;
      }
    }

    const turns = [];
    for (const agentId of selectedAgents) {
      const agent = AGENTS[agentId] || AGENTS.summary;
      const input = buildAgentMeetingInput({
        agent,
        agentId,
        project,
        question,
        paperText,
        projectSummary,
        agentMemory: agentMemories[agentId],
        mode,
        priorTurns: turns
      });
      const meetingExtra = agentId === "perplexity"
        ? "SEARCH OPENER. Answer first. Use maximum 5 short bullets. Include 2-4 usable links or search URLs, such as PubMed or Google Scholar query links, plus what later professors should verify. End with the marker: Done."
        : "MEETING MODE. Answer as one member of a research meeting. Maximum 4 complete bullets. Use any prior Perplexity search signals as context, but do not repeat them. Include: your view, main concern, best next action, and one question for another agent. Avoid repeating the paper details. End with the marker: Done.";
      const instructions = buildInstructions({
        agent,
        mode,
        extra: meetingExtra,
        customPrompt: customPromptFor(customPrompts, agentId)
      });
      const result = await callModel({
        env,
        request,
        agentId,
        instructions,
        input,
        maxTokens: Math.min(mode.maxOutputTokens, AGENT_TOKENS)
      });
      const turn = {
        agent: agentId,
        label: agent.label,
        provider: result.provider,
        model: result.model,
        output: result.output
      };
      turns.push(turn);
      if (memoryAvailable) await saveMeetingTurn(db, meetingId, agentId, "agent", result.output);
    }

    const finalAgentId = finalSynthesizer(project.mode);
    const finalResult = await synthesizeFinal({
      env,
      request,
      project,
      question,
      paperText,
      projectSummary,
      finalMemory: agentMemories[finalAgentId],
      turns,
      mode,
      finalAgentId,
      customPrompts
    });
    if (memoryAvailable) await saveMeetingTurn(db, meetingId, finalAgentId, "synthesis", finalResult.output);

    const active = activeMeeting
      ? await runActiveMeeting({
          env,
          request,
          project,
          question,
          paperText,
          turns,
          synthesis: finalResult.output,
          mode,
          customPrompts
        })
      : null;

    const memoryUpdates = buildMemoryUpdates({ project, question, turns, synthesis: finalResult.output, synthesisLabel: AGENTS[finalAgentId].label });
    if (memoryAvailable) {
      for (const turn of turns) {
        await upsertAgentMemory(db, project.id, turn.agent, compactMemory(agentMemories[turn.agent], turn.output));
      }
      await upsertAgentMemory(db, project.id, finalAgentId, compactMemory(agentMemories[finalAgentId], finalResult.output));
      await upsertProjectSummary(db, project.id, memoryUpdates.projectSummary);
    }

    return json({
      meeting_id: meetingId,
      memory_enabled: memoryAvailable,
      memory_warning: memoryWarning,
      project_summary: memoryUpdates.projectSummary,
      turns,
      synthesis: {
        agent: finalAgentId,
        label: AGENTS[finalAgentId].label,
        provider: finalResult.provider,
        model: finalResult.model,
        output: finalResult.output
      },
      active
    });
  } catch (error) {
    return json({ error: error.message || "Meeting failed." }, 500);
  }
}

async function runActiveMeeting({ env, request, project, question, paperText, turns, synthesis, mode, customPrompts }) {
  const questionAgentId = project.mode === "research" ? "fisher" : "neo";
  const followup = await generateFollowupQuestion({
    env,
    request,
    project,
    question,
    paperText,
    turns,
    synthesis,
    mode,
    questionAgentId,
    customPrompts
  });
  const answers = [];
  for (const agentId of ["fisher", "neo"]) {
    const result = await answerFollowup({
      env,
      request,
      project,
      originalQuestion: question,
      followupQuestion: followup.output,
      turns,
      synthesis,
      mode,
      agentId,
      customPrompts
    });
    answers.push({
      agent: agentId,
      label: AGENTS[agentId].label,
      provider: result.provider,
      model: result.model,
      output: result.output
    });
  }
  return {
    question: followup.output,
    question_by: questionAgentId,
    answers
  };
}

async function generateFollowupQuestion({ env, request, project, question, paperText, turns, synthesis, mode, questionAgentId, customPrompts }) {
  const agent = AGENTS[questionAgentId];
  const input = [
    `Project mode: ${project.mode}`,
    project.topic ? `Topic:\n${project.topic}` : "",
    project.paperTitle ? `Paper title/source:\n${project.paperTitle}` : "",
    paperText ? `Context excerpt:\n${paperText.slice(0, 1400)}` : "",
    question ? `Original question:\n${question}` : "",
    "Agent answers:",
    turns.map((turn) => `${turn.label}: ${turn.output.slice(0, 420)}`).join("\n"),
    `Final synthesis:\n${synthesis.slice(0, 900)}`,
    "",
    "Create exactly ONE follow-up question that would move this meeting forward. Make it specific, decision-oriented, and answerable by experts. Return only the question."
  ]
    .filter(Boolean)
    .join("\n\n");
  return callModel({
    env,
    request,
    agentId: questionAgentId,
    instructions: buildInstructions({
      agent,
      mode,
      extra: "ACTIVE MEETING. Generate one high-value follow-up question only.",
      customPrompt: customPromptFor(customPrompts, questionAgentId)
    }),
    input,
    maxTokens: 160
  });
}

async function answerFollowup({ env, request, project, originalQuestion, followupQuestion, turns, synthesis, mode, agentId, customPrompts }) {
  const agent = AGENTS[agentId];
  const input = [
    `Project mode: ${project.mode}`,
    project.topic ? `Topic:\n${project.topic}` : "",
    originalQuestion ? `Original question:\n${originalQuestion}` : "",
    `Follow-up question:\n${followupQuestion}`,
    "Prior agent answer summary:",
    turns.map((turn) => `${turn.label}: ${turn.output.slice(0, 300)}`).join("\n"),
    `Prior synthesis:\n${synthesis.slice(0, 700)}`,
    "",
    "Answer the follow-up in maximum 4 complete bullets. Focus on decision, risk, and next action. End with the marker: Done."
  ]
    .filter(Boolean)
    .join("\n\n");
  return callModel({
    env,
    request,
    agentId,
    instructions: buildInstructions({
      agent,
      mode,
      extra: "ACTIVE MEETING FOLLOW-UP. Answer concisely; do not repeat prior discussion. Finish completely and end with the marker: Done.",
      customPrompt: customPromptFor(customPrompts, agentId)
    }),
    input,
    maxTokens: FOLLOWUP_TOKENS
  });
}

function normalizeProject(project) {
  return {
    id: clean(project.id, 80) || crypto.randomUUID(),
    title: clean(project.title, 180) || "Untitled research note",
    mode: project.mode === "journal" ? "journal" : "research",
    topic: clean(project.topic, 1400),
    journal: clean(project.journal || "generic", 80),
    paperTitle: clean(project.paperTitle, 220),
    paperText: clean(project.paperText, 6500)
  };
}

function normalizeAgents(value, mode) {
  const defaults = mode === "journal" ? ["journalclub", "methods", "stats"] : ["question", "design", "stats"];
  const allowed =
    mode === "journal"
      ? new Set(["journalclub", "methods", "stats", "clinical", "deid", "summary", "perplexity", "watson", "chen", "mimi", "osler"])
      : new Set(["literature", "question", "design", "ethics", "stats", "writing", "deid", "summary", "perplexity", "watson", "chen", "mimi", "neo", "osler", "fisher"]);
  const raw = Array.isArray(value) && value.length ? value : defaults;
  const agents = raw.filter((agent) => allowed.has(agent)).slice(0, MEETING_AGENT_LIMIT);
  if (agents.includes("perplexity")) {
    agents.sort((a, b) => (a === "perplexity" ? -1 : b === "perplexity" ? 1 : 0));
  }
  return agents.length ? agents : defaults;
}

function normalizeCustomPrompts(value) {
  if (!value || typeof value !== "object") return {};
  const prompts = {};
  for (const [agentId, prompt] of Object.entries(value)) {
    if (!AGENTS[agentId]) continue;
    const cleaned = clean(prompt, 600);
    if (cleaned) prompts[agentId] = cleaned;
  }
  return prompts;
}

function customPromptFor(prompts, agentId) {
  return clean(prompts?.[agentId], 600);
}

function buildAgentMeetingInput({ agent, agentId, project, question, paperText, projectSummary, agentMemory, mode, priorTurns = [] }) {
  const priorSearch = priorTurns
    .filter((turn) => turn.agent === "perplexity")
    .map((turn) => `${turn.label} search opener:\n${turn.output.slice(0, 1200)}`)
    .join("\n\n");
  const priorContext = !priorSearch && priorTurns.length
    ? priorTurns.map((turn) => `${turn.label}: ${turn.output.slice(0, 260)}`).join("\n")
    : "";
  return [
    `Project mode: ${project.mode}`,
    `Project title: ${project.title}`,
    project.topic ? `Topic:\n${project.topic}` : "",
    project.paperTitle ? `Paper title/source:\n${project.paperTitle}` : "",
    projectSummary ? `Compact project memory:\n${projectSummary.slice(0, 900)}` : "",
    agentMemory ? `Your compact memory:\n${agentMemory.slice(0, 650)}` : "",
    agentId !== "perplexity" && priorSearch ? `Use this search opener instead of searching again:\n${priorSearch}` : "",
    agentId !== "perplexity" && priorContext ? `Prior compact meeting context:\n${priorContext}` : "",
    paperText ? `Paper/context excerpt:\n${paperText.slice(0, mode.label === "Deep" ? 6500 : 4200)}` : "",
    question ? `Meeting question:\n${question}` : "Meeting question: What is the best research or journal club answer now?",
    "",
    `Your role: ${agent.label}`,
    "Return only compact bullets. Do not include patient identifiers."
  ]
    .filter(Boolean)
    .join("\n\n");
}

async function synthesizeFinal({ env, request, project, question, paperText, projectSummary, finalMemory, turns, mode, finalAgentId, customPrompts }) {
  const agent = AGENTS[finalAgentId] || AGENTS.neo;
  const finalTask =
    finalAgentId === "fisher"
      ? "Synthesize the best research decision. Use: Decision, Why, Weakest assumption, Design/stat risk, Next action, Question for data/stat team."
      : "Synthesize the best journal club answer. Use: Decision, Why it matters, Weakest point, Best next action, Question to ask in journal club/research meeting.";
  const input = [
    `Project mode: ${project.mode}`,
    `Project title: ${project.title}`,
    project.topic ? `Topic:\n${project.topic}` : "",
    project.paperTitle ? `Paper title/source:\n${project.paperTitle}` : "",
    projectSummary ? `Compact project memory:\n${projectSummary.slice(0, 900)}` : "",
    finalMemory ? `${agent.label} memory:\n${finalMemory.slice(0, 650)}` : "",
    paperText ? `Paper/context excerpt:\n${paperText.slice(0, mode.label === "Deep" ? 4200 : 2600)}` : "",
    question ? `Meeting question:\n${question}` : "",
    "Agent opinions:",
    turns.map((turn) => `## ${turn.label}\n${turn.output.slice(0, 900)}`).join("\n\n"),
    "",
    finalTask
  ]
    .filter(Boolean)
    .join("\n\n");
  const instructions = buildInstructions({
    agent,
    mode,
    extra:
      "FINAL MEETING SYNTHESIS. Be professor-level, concise, and decisive. Resolve disagreement. Do not invent facts. Maximum 6 complete bullets. End with the marker: Done.",
    customPrompt: customPromptFor(customPrompts, finalAgentId)
  });
  return callModel({
    env,
    request,
    agentId: finalAgentId,
    instructions,
    input,
    maxTokens: Math.min(mode.maxOutputTokens, NEO_TOKENS)
  });
}

function buildMemoryUpdates({ project, question, turns, synthesis, synthesisLabel }) {
  const turnSummary = turns
    .map((turn) => `${turn.label}: ${firstSentence(turn.output)}`)
    .join(" ");
  return {
    projectSummary: compactText(
      [
        `Project: ${project.title}.`,
        project.topic ? `Topic: ${project.topic}` : "",
        question ? `Latest question: ${question}` : "",
        turnSummary,
        `${synthesisLabel || "Final synthesis"}: ${firstSentence(synthesis)}`
      ].join(" "),
      1100
    )
  };
}

function finalSynthesizer(mode) {
  return mode === "research" ? "fisher" : "neo";
}

function compactMemory(existing, latest) {
  return compactText([latest, existing].filter(Boolean).join(" "), 850);
}

function firstSentence(value) {
  return compactText(String(value || "").split(/(?<=[.!?])\s+/)[0] || value, 220);
}

function compactText(value, max) {
  return String(value || "")
    .replace(/\b(HN|MRN|phone|tel|address)\s*[:#]?\s*\S+/gi, "[removed-id]")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max);
}
