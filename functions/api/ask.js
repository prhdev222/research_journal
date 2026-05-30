import { AGENTS, RESPONSE_MODES, buildInstructions, buildWritingInstructions, buildCaseReportInstructions, callModel } from "../_lib/ai.js";
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
    const section = clean(body.section || "full", 50);
    const proposalSections = Array.isArray(body.proposalSections) ? body.proposalSections : null;
    const caseSection = clean(body.caseSection || "sequence", 50);
    const caseInputMode = clean(body.caseInputMode || "write", 20);
    const customPrompt = clean(body.customPrompt, 600);

    if (!topic && !question && !notes) {
      return json({ error: "Please provide a topic, question, or notes." }, 400);
    }

    const isWriting = agentId === "writing";
    const isCaseReport = agentId === "casereport";
    const sectionLabel = isWriting && section !== "full" ? ` — ${section}` : "";
    const caseSectionLabel = isCaseReport ? ` — ${caseSection}` : "";

    const input = [
      `Agent: ${agent.label}${sectionLabel}${caseSectionLabel}`,
      !isCaseReport ? `Target journal/style: ${journal}` : "",
      topic ? `Research topic / Case title:\n${topic}` : "",
      notes ? `Working notes / Draft:\n${notes}` : "",
      question ? `User request:\n${question}` : isCaseReport ? "User request: guide me through this case report section." : "User request: suggest the next useful research step.",
      "",
      `Response mode: ${mode.label}`,
      "Return Thai or English matching the user's language.",
      "Finish the answer completely in this response. End with the marker: Done."
    ]
      .filter(Boolean)
      .join("\n\n");

    const instructions = isCaseReport
      ? buildCaseReportInstructions({ mode, section: caseSection, inputMode: caseInputMode, customPrompt })
      : isWriting
        ? buildWritingInstructions({ mode, journal, section, proposalSections, customPrompt })
        : buildInstructions({
            agent,
            mode,
            customPrompt,
            extra: "SINGLE AGENT ANSWER. Complete every requested section. End with the marker: Done."
          });
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
