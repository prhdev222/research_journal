import { AGENTS, RESPONSE_MODES, buildInstructions, callModel } from "../_lib/ai.js";
import { clean, json } from "../_lib/http.js";

const ALLOWED_INVITEES = new Set(["watson", "chen", "mimi", "osler", "perplexity", "neo", "fisher"]);

export async function onRequestPost({ request, env }) {
  try {
    const body = await request.json();
    const agentId = ALLOWED_INVITEES.has(body.agent) ? body.agent : "watson";
    const agent = AGENTS[agentId] || AGENTS.watson;
    const mode = RESPONSE_MODES[body.mode] || RESPONSE_MODES.short;
    const followupQuestion = clean(body.followupQuestion, 1000);
    const context = clean(body.context, 4500);
    const customPrompt = clean(body.customPrompt || body.customPrompts?.[agentId], 600);

    if (!followupQuestion) return json({ error: "Missing follow-up question." }, 400);

    const result = await callModel({
      env,
      request,
      agentId,
      instructions: buildInstructions({
        agent,
        mode,
        extra: "INVITED ACTIVE MEETING GUEST. Answer only the follow-up. Maximum 4 complete bullets. End with the marker: Done.",
        customPrompt
      }),
      input: [
        `Follow-up question:\n${followupQuestion}`,
        context ? `Meeting context:\n${context}` : "",
        "Give a concise expert answer with decision, risk, and next action."
      ]
        .filter(Boolean)
        .join("\n\n"),
      maxTokens: agentId === "osler" ? 900 : 760
    });

    return json({
      agent: agentId,
      label: agent.label,
      provider: result.provider,
      model: result.model,
      output: result.output
    });
  } catch (error) {
    return json({ error: error.message || "Follow-up failed." }, 500);
  }
}
