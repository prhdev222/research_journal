const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store"
};

export async function onRequestPost({ request }) {
  try {
    const body = await request.json();
    const url = normalizeUrl(body.url);
    if (!url) return json({ error: "Please provide a valid http/https paper link." }, 400);
    if (isBlockedHost(url.hostname)) return json({ error: "This host is not allowed." }, 400);

    const upstream = await fetch(url.toString(), {
      headers: {
        "user-agent": "Research-Assistant/0.1",
        accept: "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"
      },
      redirect: "follow"
    });

    if (!upstream.ok) {
      return json({ error: `Could not fetch paper link (${upstream.status}).` }, upstream.status);
    }

    const type = upstream.headers.get("content-type") || "";
    if (type.includes("application/pdf")) {
      return json(
        {
          error:
            "This link points to a PDF. Download it and use Upload PDF so text extraction happens in your browser."
        },
        415
      );
    }

    const html = await upstream.text();
    const title = extractTitle(html) || url.hostname;
    const text = extractReadableText(html).slice(0, 16000);

    if (text.length < 120) {
      return json({ error: "Could not extract enough readable text from this link." }, 422);
    }

    return json({ url: url.toString(), title, text });
  } catch (error) {
    return json({ error: error.message || "Could not read paper link." }, 500);
  }
}

function normalizeUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    if (!["http:", "https:"].includes(url.protocol)) return null;
    return url;
  } catch {
    return null;
  }
}

function isBlockedHost(hostname) {
  const host = hostname.toLowerCase();
  return (
    host === "localhost" ||
    host.endsWith(".localhost") ||
    host === "127.0.0.1" ||
    host === "0.0.0.0" ||
    host === "::1" ||
    host.startsWith("10.") ||
    host.startsWith("192.168.") ||
    /^172\.(1[6-9]|2\d|3[0-1])\./.test(host)
  );
}

function extractTitle(html) {
  const match =
    html.match(/<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']/i) ||
    html.match(/<meta[^>]+name=["']citation_title["'][^>]+content=["']([^"']+)["']/i) ||
    html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return match ? decodeEntities(stripTags(match[1])).trim() : "";
}

function extractReadableText(html) {
  return decodeEntities(
    html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
      .replace(/<(h1|h2|h3|h4|p|li|abstract|section|article|div)\b[^>]*>/gi, "\n")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .replace(/\s*\n\s*/g, "\n")
  ).trim();
}

function stripTags(value) {
  return String(value || "").replace(/<[^>]+>/g, " ");
}

function decodeEntities(value) {
  return String(value || "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: JSON_HEADERS
  });
}
