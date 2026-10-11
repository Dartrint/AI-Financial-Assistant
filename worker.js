const securityHeaders = {
  "Content-Security-Policy":
    "default-src 'self'; connect-src 'self' https://*.supabase.co wss://*.supabase.co; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
};

const aiModel = "@cf/qwen/qwen3-30b-a3b-fp8";
const maxAiRequestBytes = 24_000;
const encoder = new TextEncoder();

function json(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: securityHeaders,
  });
}

async function readBoundedBody(request) {
  const reader = request.body?.getReader();
  if (!reader) return "";

  const chunks = [];
  let totalBytes = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    totalBytes += value.byteLength;
    if (totalBytes > maxAiRequestBytes) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }

  const body = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder().decode(body);
}

async function hasValidSignature(request, body, secret) {
  const timestamp = request.headers.get("x-findata-timestamp");
  const signature = request.headers.get("x-findata-signature");
  if (
    !timestamp ||
    !/^\d{13}$/.test(timestamp) ||
    Math.abs(Date.now() - Number(timestamp)) > 60_000 ||
    !signature ||
    !/^[\da-f]{64}$/i.test(signature)
  ) {
    return false;
  }

  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"],
  );
  const signatureBytes = Uint8Array.from(
    signature.match(/.{2}/g),
    (byte) => Number.parseInt(byte, 16),
  );
  return crypto.subtle.verify(
    "HMAC",
    key,
    signatureBytes,
    encoder.encode(`${timestamp}.${body}`),
  );
}

async function handleAiRequest(request, env) {
  if (request.method !== "POST") {
    return json({ error: "Method Not Allowed" }, 405);
  }
  if (!env.AI_PROXY_SECRET || env.AI_PROXY_SECRET.length < 32) {
    console.error("Workers AI proxy secret is missing or too short.");
    return json({ error: "Workers AI proxy is not configured." }, 503);
  }

  let body;
  try {
    body = await readBoundedBody(request);
  } catch (error) {
    console.error(
      "Workers AI proxy could not read the request body.",
      error instanceof Error ? error.message : "Unknown error",
    );
    return json({ error: "Could not read request body." }, 400);
  }
  if (body === null) {
    return json({ error: "Request body is too large." }, 413);
  }
  if (!await hasValidSignature(request, body, env.AI_PROXY_SECRET)) {
    return json({ error: "Unauthorized." }, 401);
  }

  let payload;
  try {
    payload = JSON.parse(body);
  } catch {
    return json({ error: "Request body must be valid JSON." }, 400);
  }
  if (
    typeof payload !== "object" ||
    payload === null ||
    !Array.isArray(payload.messages) ||
    payload.messages.length < 2 ||
    payload.messages.length > 8 ||
    payload.messages.some((message) =>
      typeof message !== "object" ||
      message === null ||
      !["system", "user", "assistant"].includes(message.role) ||
      typeof message.content !== "string" ||
      message.content.length === 0 ||
      message.content.length > 8_000
    )
  ) {
    return json({ error: "Invalid AI messages." }, 400);
  }

  try {
    const result = await env.AI.run(aiModel, {
      messages: payload.messages,
      temperature: 0.25,
      max_tokens: 1_200,
    });
    if (typeof result?.response !== "string" || !result.response.trim()) {
      console.error("Workers AI returned an empty response.");
      return json({ error: "Workers AI returned an empty response." }, 502);
    }
    return json({ answer: result.response.trim() });
  } catch (error) {
    console.error(
      "Workers AI inference failed.",
      error instanceof Error ? error.message : "Unknown error",
    );
    return json({ error: "Workers AI inference failed." }, 502);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/internal/ai") {
      return handleAiRequest(request, env);
    }

    if (url.pathname === "/config.js") {
      if (request.method !== "GET") {
        return new Response("Method Not Allowed", {
          status: 405,
          headers: { Allow: "GET" },
        });
      }

      const config = {
        supabaseUrl: env.SUPABASE_URL,
        supabasePublishableKey: env.SUPABASE_PUBLISHABLE_KEY,
      };
      return new Response(
        `window.FINDATA_CONFIG=${JSON.stringify(config)};`,
        {
          headers: {
            ...securityHeaders,
            "Cache-Control": "no-store",
            "Content-Type": "application/javascript; charset=utf-8",
          },
        },
      );
    }

    const response = await env.ASSETS.fetch(request);
    const headers = new Headers(response.headers);
    for (const [name, value] of Object.entries(securityHeaders)) {
      headers.set(name, value);
    }

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
