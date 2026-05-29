import { callModel } from "../_lib/ai.js";
import { clean, json } from "../_lib/http.js";

export async function onRequestPost({ request, env }) {
  try {
    const body = await request.json();
    const text = clean(body.text, 18000);
    if (!text) return json({ error: "No text to translate." }, 400);

    const instructions = [
      "You are a careful Thai medical/research translator.",
      "Translate the provided research or journal-club result into natural Thai.",
      "Preserve headings, bullet structure, numbers, abbreviations, drug names, statistics, and citations.",
      "Do not add new analysis. Do not remove uncertainty markers such as verify.",
      "Use concise professional Thai suitable for a Thai physician/researcher."
    ].join("\n");

    const chunks = splitForTranslation(text);
    const outputs = [];
    let provider = "";
    let model = "";

    for (let index = 0; index < chunks.length; index += 1) {
      const result = await callModel({
        env,
        request,
        agentId: "translate",
        instructions,
        input: [
          chunks.length > 1 ? `Part ${index + 1} of ${chunks.length}. Translate only this part.` : "",
          chunks[index]
        ]
          .filter(Boolean)
          .join("\n\n"),
        maxTokens: 2600,
        fallbackModel: env.OPENROUTER_MODEL_TRANSLATE || env.OPENROUTER_MODEL || "openrouter/auto"
      });
      provider = result.provider;
      model = result.model;
      outputs.push(result.output);
    }

    return json({
      provider,
      model,
      parts: chunks.length,
      output: outputs.join("\n\n")
    });
  } catch (error) {
    return json({ error: error.message || "Thai translation failed." }, 500);
  }
}

function splitForTranslation(text) {
  const maxChars = 3200;
  if (text.length <= maxChars) return [text];

  const blocks = text.split(/\n(?=#{1,3}\s|\*\*[^*]+\*\*:)/g);
  const chunks = [];
  let current = "";

  for (const block of blocks) {
    if ((current + "\n" + block).length <= maxChars) {
      current = current ? `${current}\n${block}` : block;
      continue;
    }
    if (current) chunks.push(current);
    if (block.length <= maxChars) {
      current = block;
      continue;
    }
    for (let start = 0; start < block.length; start += maxChars) {
      chunks.push(block.slice(start, start + maxChars));
    }
    current = "";
  }

  if (current) chunks.push(current);
  return chunks.slice(0, 8);
}
