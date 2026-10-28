// 127.0.0.1 (not localhost): on Windows localhost can resolve to IPv6 first while uvicorn listens on IPv4.
const BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function headers() {
  const token = sessionStorage.getItem("token");
  return { "Content-Type": "application/json", ...(token && { Authorization: `Bearer ${token}` }) };
}

async function send(path, { method = "GET", body } = {}) {
  try {
    return await fetch(BASE + path, { method, headers: headers(), body: body && JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }
}

/** Throws ApiError for non-2xx responses; handles session expiry. */
async function check(res, path) {
  if (res.status === 401 && path !== "/auth/login") {
    sessionStorage.clear();
    window.location.href = "/login";
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : data.error ?? detail;
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail);
  }
  return res;
}

/** Single place for all JSON HTTP calls. Adds the JWT and handles session expiry. */
export async function api(path, options = {}) {
  const res = await check(await send(path, options), path);
  return res.json();
}

/**
 * POST /chat/stream and call onEvent(type, data) for every Server-Sent Event as it arrives
 * (tool / step / status / agent events, then one "final" event with the verified response).
 * Returns the final response.
 */
export async function streamChat(body, onEvent) {
  const res = await check(await send("/chat/stream", { method: "POST", body }), "/chat/stream");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let type = "message";
      let data = "";
      for (const line of chunk.split("\n")) {
        if (line.startsWith("event:")) type = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue; // comment / keep-alive
      const parsed = JSON.parse(data);
      if (type === "final") final = parsed.response;
      else onEvent(type, parsed);
    }
  }
  if (!final) throw new ApiError(0, "The answer stream ended unexpectedly. Please try again.");
  return final;
}
