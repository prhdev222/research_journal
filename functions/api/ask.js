import { AGENTS, RESPONSE_MODES, buildInstructions, callModel } from "../_lib/ai.js";
import { clean, json } from "../_lib/http.js";

export async function onRequestPost({ request, env }) {
  try {
    const body = await request.json();
    const agentId = String(body.agent || "summary");
    const agent = AGENTS[agentId] || AGENTS.summary;
    const modeId = RESPONSE_MODES[body.mode] ? body.mode : "short";
    const mode = RESPONSE_MODES[modeId];
    const topic = clean(body.topic, mode.topicLimit);
    const question = clean(body.question, mode.questionLimit);
    const notes = clean(body.notes, mode.notesLimit);
    const journal = clean(body.journal || "generic", 80);
    const customPrompt = clean(body.customPrompt, 600);

    if (!topic && !question && !notes) {
      return json({ error: "Please provide a topic, question, or notes." }, 400);
    }

    const input = [
      `Agent: ${agent.label}`,
      `Target journal/style: ${journal}`,
      topic ? `Research topic:\n${topic}` : "",
      notes ? `Working notes:\n${notes}` : "",
      question ? `User request:\n${question}` : "User request: suggest the next useful research step.",
      "",
      `Response mode: ${mode.label}`,
      mode.prompt,
      "Return Thai or English matching the user's language."
    ]
      .filter(Boolean)
      .join("\n\n");

    const instructions = buildInstructions({ agent, mode, customPrompt });
    const result = await callModel({
      env,
      request,
      agentId,
      instructions,
      input,
      maxTokens: mode.maxOutputTokens
    });

    return json({
      agent: agentId,
      label: agent.label,
      mode: modeId,
      provider: result.provider,
      model: result.model,
      output: result.output,
      raw_id: result.id || null
    });
  } catch (error) {
    return json({ error: error.message || "Unexpected server error." }, 500);
  }
}
