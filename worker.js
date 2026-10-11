const securityHeaders = {
  "Content-Security-Policy":
    "default-src 'self'; connect-src 'self' https://*.supabase.co wss://*.supabase.co; img-src 'self' data:; style-src 'self'; script-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

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
