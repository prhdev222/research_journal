const COOKIE_NAME = "jeda_auth";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;

export function authConfigured(env) {
  return Boolean(clean(env.ACCESS_CODES) || clean(env.ADMIN_CODE));
}

export async function roleForCode(env, code) {
  const value = clean(code);
  if (!value) return "";
  if (clean(env.ADMIN_CODE) && timingSafeEqual(value, clean(env.ADMIN_CODE))) return "admin";
  const codes = clean(env.ACCESS_CODES)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return codes.some((item) => timingSafeEqual(value, item)) ? "user" : "";
}

export async function createSessionCookie(env, request, role) {
  const exp = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const payload = `v1.${exp}.${role === "admin" ? "admin" : "user"}`;
  const sig = await sign(env, payload);
  const secure = new URL(request.url).protocol === "https:" ? " Secure;" : "";
  return `${COOKIE_NAME}=${payload}.${sig}; HttpOnly;${secure} SameSite=Lax; Path=/; Max-Age=${SESSION_TTL_SECONDS}`;
}

export async function clearSessionCookie(request) {
  const secure = new URL(request.url).protocol === "https:" ? " Secure;" : "";
  return `${COOKIE_NAME}=; HttpOnly;${secure} SameSite=Lax; Path=/; Max-Age=0`;
}

export async function verifySession(env, request) {
  if (!authConfigured(env)) return { ok: true, role: "disabled" };
  const token = parseCookies(request.headers.get("cookie") || "")[COOKIE_NAME];
  if (!token) return { ok: false, role: "" };
  const parts = token.split(".");
  if (parts.length !== 4 || parts[0] !== "v1") return { ok: false, role: "" };
  const payload = parts.slice(0, 3).join(".");
  const exp = Number(parts[1]);
  const role = parts[2];
  if (!Number.isFinite(exp) || exp < Math.floor(Date.now() / 1000)) return { ok: false, role: "" };
  if (role !== "admin" && role !== "user") return { ok: false, role: "" };
  const expected = await sign(env, payload);
  return timingSafeEqual(parts[3], expected) ? { ok: true, role } : { ok: false, role: "" };
}

export function unauthorizedJson() {
  return new Response(JSON.stringify({ error: "Authentication required." }), {
    status: 401,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
  });
}

export function loginPage() {
  return new Response(
    `<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#f7f1e7">
  <title>Research Access</title>
  <style>
    :root { color-scheme: light; --ink:#17211e; --muted:#5e6a64; --line:rgba(32,45,39,.14); --paper:#fffdf7; --bench:#f7f1e7; --teal:#0e6f73; --red:#9e2f3e; }
    * { box-sizing: border-box; }
    body { margin:0; min-height:100vh; display:grid; place-items:center; padding:18px; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color:var(--ink); background:linear-gradient(90deg, rgba(14,111,115,.045) 1px, transparent 1px) 0 0 / 28px 28px, linear-gradient(rgba(159,47,62,.035) 1px, transparent 1px) 0 0 / 28px 28px, var(--bench); }
    main { width:min(420px,100%); border:1px solid var(--line); border-radius:8px; background:rgba(255,253,247,.94); box-shadow:0 18px 48px rgba(55,43,27,.12); overflow:hidden; }
    header { padding:18px 18px 12px; border-bottom:1px solid var(--line); }
    h1 { margin:0; font-size:22px; line-height:1.15; }
    p { margin:7px 0 0; color:var(--muted); font-size:13px; line-height:1.45; }
    form { display:grid; gap:12px; padding:18px; }
    label { display:grid; gap:7px; color:var(--muted); font-size:12px; font-weight:800; }
    input { width:100%; min-height:48px; border:1px solid var(--line); border-radius:8px; padding:0 12px; background:#f8f2e8; color:var(--ink); font:inherit; }
    input:focus { outline:none; border-color:rgba(14,111,115,.65); box-shadow:0 0 0 3px rgba(14,111,115,.12); }
    button { min-height:48px; border:0; border-radius:8px; background:var(--teal); color:white; font-weight:850; cursor:pointer; }
    .error { min-height:18px; color:var(--red); font-size:12px; font-weight:750; }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Research Access</h1>
      <p>ใส่รหัสที่ admin ให้ก่อนใช้งาน AI และ journal club</p>
    </header>
    <form id="loginForm">
      <label>
        Access code
        <input id="codeInput" name="code" type="password" autocomplete="current-password" autofocus required>
      </label>
      <button id="submitBtn" type="submit">Enter</button>
      <div class="error" id="errorText"></div>
    </form>
  </main>
  <script>
    document.getElementById("loginForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = document.getElementById("submitBtn");
      const error = document.getElementById("errorText");
      button.disabled = true;
      error.textContent = "";
      try {
        const res = await fetch("/api/login", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ code: document.getElementById("codeInput").value })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Login failed.");
        location.reload();
      } catch (err) {
        error.textContent = err.message;
      } finally {
        button.disabled = false;
      }
    });
  </script>
</body>
</html>`,
    { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } }
  );
}

async function sign(env, payload) {
  const secret = clean(env.AUTH_SECRET) || clean(env.OPENROUTER_API_KEY) || clean(env.ADMIN_CODE) || clean(env.ACCESS_CODES);
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  return base64Url(sig);
}

function parseCookies(cookieHeader) {
  return Object.fromEntries(
    cookieHeader
      .split(";")
      .map((part) => part.trim().split("="))
      .filter(([key]) => key)
      .map(([key, ...value]) => [key, value.join("=")])
  );
}

function base64Url(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function timingSafeEqual(a, b) {
  const left = String(a || "");
  const right = String(b || "");
  let diff = left.length ^ right.length;
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    diff |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }
  return diff === 0;
}

function clean(value) {
  return String(value || "").trim();
}
