import { authConfigured, loginPage, unauthorizedJson, verifySession } from "./_lib/auth.js";

const PUBLIC_PATHS = new Set(["/api/login"]);

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (!authConfigured(context.env) || PUBLIC_PATHS.has(url.pathname)) {
    return context.next();
  }

  const session = await verifySession(context.env, context.request);
  if (session.ok) {
    return context.next();
  }

  if (url.pathname.startsWith("/api/")) {
    return unauthorizedJson();
  }

  return loginPage();
}
