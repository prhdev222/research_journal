import { authConfigured, verifySession } from "../_lib/auth.js";
import { json } from "../_lib/http.js";

export async function onRequestGet({ request, env }) {
  const session = await verifySession(env, request);
  return json({
    authenticated: session.ok,
    role: session.role === "disabled" ? "admin" : session.role || "guest",
    auth_configured: authConfigured(env)
  });
}
