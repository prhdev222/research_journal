import { createSessionCookie, roleForCode } from "../_lib/auth.js";
import { clean, json } from "../_lib/http.js";

export async function onRequestPost({ request, env }) {
  try {
    const body = await request.json();
    const code = clean(body.code, 200);
    const role = await roleForCode(env, code);
    if (!role) {
      return json({ error: "Invalid access code." }, 401);
    }
    return json(
      { ok: true, role },
      200,
      {
        "set-cookie": await createSessionCookie(env, request, role)
      }
    );
  } catch (error) {
    return json({ error: error.message || "Login failed." }, 500);
  }
}
