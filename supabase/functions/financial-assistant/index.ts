import { withSupabase } from "npm:@supabase/server@1";

const supportedSymbols = [
  "VCB", "BID", "CTG", "VNM", "FPT", "VIC", "MSN", "VJC",
  "SAB", "HPG", "MWG", "VRE", "HDB", "TCB", "VPB",
];

const systemPrompt = [
  "Bạn là trợ lý giáo dục tài chính thân thiện, trả lời bằng tiếng Việt tự nhiên và có cấu trúc Markdown dễ đọc.",
  "Trả lời trực tiếp trước, sau đó giải thích ý nghĩa, công thức, cách áp dụng và giới hạn khi phù hợp.",
  "Dùng tiêu đề ngắn, danh sách hoặc bảng khi giúp người đọc so sánh; giải thích thuật ngữ chuyên môn ngay lần đầu xuất hiện.",
  "Viết công thức bằng ký hiệu văn bản dễ đọc như `ROE = lợi nhuận ròng / vốn chủ sở hữu`; không dùng cú pháp LaTeX.",
  "Ví dụ số chỉ được dùng nếu ghi rõ là ví dụ giả định; không biến ví dụ thành dữ liệu thực tế hay khuyến nghị.",
  "Chỉ sử dụng dữ liệu giá được cung cấp trong ngữ cảnh của câu hỏi; không tự bổ sung số liệu, báo cáo hoặc ngày tháng.",
  "Nếu dữ liệu được cung cấp không đủ để kết luận, hãy nêu rõ giới hạn đó.",
  "Không đưa ra khuyến nghị mua, bán hay lời khuyên đầu tư cá nhân hóa.",
].join(" ");

const json = (payload: unknown, status = 200) =>
  Response.json(payload, { status });

type MarketQuote = {
  symbol: string;
  name: string;
  price: number;
  previousClose: number | null;
  change: number | null;
  changePercent: number | null;
  volume: number | null;
  asOf: number | null;
  currency: string;
  source: string;
  sourceUrl: string;
};

type MarketChart = {
  title: string;
  labels: string[];
  values: number[];
  unit: string;
  source: string;
  asOf: number | null;
};

type HistoricalPoint = {
  timestamp: number;
  close: number;
  volume: number | null;
};

const chartPeriods = {
  "1mo": { interval: "1d", label: "1 tháng" },
  "3mo": { interval: "1d", label: "3 tháng" },
  "6mo": { interval: "1d", label: "6 tháng" },
  "1y": { interval: "1d", label: "1 năm" },
  "5y": { interval: "1wk", label: "5 năm" },
} as const;

let marketCache: { expiresAt: number; quotes: MarketQuote[]; unavailableSymbols: string[] } | null = null;
let marketRequest: Promise<{ quotes: MarketQuote[]; unavailableSymbols: string[] }> | null = null;
const historicalChartCache = new Map<
  string,
  { expiresAt: number; data: { points: HistoricalPoint[]; name: string; currency: string } }
>();
const guestRequests = new Map<string, number[]>();
const GUEST_REQUEST_LIMIT = 5;
const GUEST_WINDOW_MS = 60_000;

function getQuestionSymbol(question: string): string | null {
  const normalized = question.normalize("NFC");
  return supportedSymbols.find((symbol) =>
    new RegExp(`\\b${symbol}\\b`, "i").test(normalized)
  ) ?? null;
}

function requiresMarketData(question: string): boolean {
  const normalized = question.normalize("NFC");
  const asksForVisualization =
    /biểu đồ|đồ thị|chart|diễn biến giá|lịch sử giá|xu hướng giá/i.test(normalized);
  const asksForHistoricalData =
    /lịch sử\s+(?:giá|doanh thu|lợi nhuận|cổ tức|vốn hóa)|xu hướng\s+(?:giá|doanh thu|lợi nhuận)|theo ngày|theo tuần|theo tháng|so với năm ngoái|\b\d+\s*(?:ngày|tuần|tháng|năm)/i
      .test(normalized);
  const asksForMetric =
    /giá|thị giá|p\s*\/\s*e|p\s*\/\s*b|doanh thu|lợi nhuận|cổ tức|vốn hóa|roe|roa|eps|báo cáo tài chính|lưu chuyển tiền|khối lượng|volume|cpi|gdp|tỷ giá|lãi suất|vn.?index|vàng|bitcoin|thị trường chứng khoán/i
      .test(normalized);
  const hasUnknownTicker = /\b[A-Z]{3}\b/.test(normalized) &&
    !/\b(?:ROE|ROA|EPS|GDP|CPI|ETF|NAV|DCF)\b/.test(normalized);
  const hasTicker = Boolean(getQuestionSymbol(normalized)) || hasUnknownTicker;
  const asksForCurrentQuote =
    /hôm nay|hiện tại|mới nhất|gần nhất|bao nhiêu|tăng|giảm|biến động|đóng cửa/i
      .test(normalized);
  const asksForPeriod =
    /hiện tại|hôm nay|mới nhất|gần nhất|bao nhiêu|năm\s*20\d{2}|quý\s*[1-4]|20\d{2}/i
      .test(normalized);

  return (hasTicker && (asksForMetric || asksForCurrentQuote)) ||
    (asksForMetric && asksForPeriod) ||
    asksForVisualization ||
    asksForHistoricalData;
}

function isQuoteOnlyQuestion(question: string): boolean {
  const normalized = question.normalize("NFC");
  return /giá|thị giá|đóng cửa|tăng|giảm|biến động|khối lượng|volume|cao nhất|thấp nhất|biểu đồ|đồ thị|chart|diễn biến giá/i
    .test(normalized) &&
    !/lịch sử|xu hướng|theo ngày|theo tuần|theo tháng|so với năm ngoái|quý\s*[1-4]|năm\s*20\d{2}|\b\d+\s*(?:ngày|tuần|tháng|năm)/i
      .test(normalized) &&
    !/p\s*\/\s*e|p\s*\/\s*b|doanh thu|lợi nhuận|cổ tức|vốn hóa|roe|roa|eps|báo cáo tài chính|lưu chuyển tiền/i
      .test(question.normalize("NFC"));
}

async function fetchMarketQuote(symbol: string): Promise<MarketQuote> {
  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}.VN`,
  );
  url.searchParams.set("range", "1d");
  url.searchParams.set("interval", "1d");

  const response = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 Findata financial assistant" },
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) {
    throw new Error(`Market provider returned HTTP ${response.status}`);
  }

  const payload = await response.json();
  const result = payload?.chart?.result?.[0];
  const meta = result?.meta;
  const quote = result?.indicators?.quote?.[0];
  const price = meta?.regularMarketPrice ??
    quote?.close?.filter((value: unknown) => typeof value === "number").at(-1);
  if (typeof price !== "number" || !Number.isFinite(price)) {
    throw new Error("Market provider returned no valid price");
  }

  const previousClose = typeof meta.chartPreviousClose === "number"
    ? meta.chartPreviousClose
    : null;
  const change = previousClose === null ? null : price - previousClose;
  const changePercent = typeof meta.regularMarketChangePercent === "number"
    ? meta.regularMarketChangePercent
    : previousClose && change !== null
    ? (change / previousClose) * 100
    : null;

  return {
    symbol,
    name: meta.longName ?? meta.shortName ?? symbol,
    price,
    previousClose,
    change,
    changePercent,
    volume: typeof meta.regularMarketVolume === "number"
      ? meta.regularMarketVolume
      : quote?.volume?.filter((value: unknown) => typeof value === "number").at(-1) ?? null,
    asOf: typeof meta.regularMarketTime === "number"
      ? meta.regularMarketTime * 1000
      : typeof result.timestamp?.at(-1) === "number"
      ? result.timestamp.at(-1) * 1000
      : null,
    currency: meta.currency ?? "VND",
    source: "Yahoo Finance",
    sourceUrl: `https://finance.yahoo.com/quote/${symbol}.VN/`,
  };
}

async function getMarketSnapshot() {
  if (marketCache && marketCache.expiresAt > Date.now()) {
    return {
      quotes: marketCache.quotes,
      unavailableSymbols: marketCache.unavailableSymbols,
    };
  }
  if (marketRequest) return await marketRequest;

  marketRequest = (async () => {
    const results = await Promise.allSettled(
      supportedSymbols.map((symbol) => fetchMarketQuote(symbol)),
    );
    const quotes: MarketQuote[] = [];
    const unavailableSymbols: string[] = [];
    for (const [index, result] of results.entries()) {
      if (result.status === "fulfilled") {
        quotes.push(result.value);
      } else {
        unavailableSymbols.push(supportedSymbols[index]);
        console.error(
          `Market quote failed for ${supportedSymbols[index]}: ${
            result.reason instanceof Error ? result.reason.message : "unknown error"
          }`,
        );
      }
    }

    if (!quotes.length) {
      throw new Error("Market provider returned no quotes");
    }

    marketCache = {
      expiresAt: Date.now() + 60_000,
      quotes,
      unavailableSymbols,
    };
    return { quotes, unavailableSymbols };
  })();

  try {
    return await marketRequest;
  } finally {
    marketRequest = null;
  }
}

async function fetchHistoricalChart(symbol: string, range: keyof typeof chartPeriods) {
  const cacheKey = `${symbol}:${range}`;
  const cached = historicalChartCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) return cached.data;

  const url = new URL(
    `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}.VN`,
  );
  url.searchParams.set("range", range);
  url.searchParams.set("interval", chartPeriods[range].interval);

  const response = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 Findata financial assistant" },
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    throw new Error(`Historical market provider returned HTTP ${response.status}`);
  }

  const payload = await response.json();
  const result = payload?.chart?.result?.[0];
  const timestamps = result?.timestamp;
  const quote = result?.indicators?.quote?.[0];
  if (!Array.isArray(timestamps) || !Array.isArray(quote?.close)) {
    throw new Error("Historical market provider returned no price series");
  }

  const points: HistoricalPoint[] = [];
  for (let index = 0; index < timestamps.length; index += 1) {
    const timestamp = timestamps[index];
    const close = quote.close[index];
    if (
      typeof timestamp === "number" &&
      Number.isFinite(timestamp) &&
      typeof close === "number" &&
      Number.isFinite(close) &&
      close >= 0
    ) {
      const volume = quote.volume?.[index];
      points.push({
        timestamp: timestamp * 1000,
        close,
        volume: typeof volume === "number" && Number.isFinite(volume) && volume >= 0
          ? volume
          : null,
      });
    }
  }
  if (!points.length) {
    throw new Error("Historical market provider returned no valid price points");
  }

  const data = {
    points,
    name: result.meta?.longName ?? result.meta?.shortName ?? symbol,
    currency: result.meta?.currency ?? "VND",
  };
  historicalChartCache.set(cacheKey, {
    expiresAt: Date.now() + 5 * 60_000,
    data,
  });
  if (historicalChartCache.size > 100) {
    for (const [key, value] of historicalChartCache) {
      if (value.expiresAt <= Date.now()) historicalChartCache.delete(key);
      if (historicalChartCache.size <= 80) break;
    }
  }
  return data;
}

function allowGuestRequest(request: Request, limit = GUEST_REQUEST_LIMIT): boolean {
  const forwardedFor = request.headers.get("x-forwarded-for");
  const clientIp = request.headers.get("cf-connecting-ip") ??
    forwardedFor?.split(",")[0]?.trim() ??
    "unknown";
  const bucketKey = `${limit}:${clientIp}`;
  const now = Date.now();
  const recentRequests = (guestRequests.get(bucketKey) ?? [])
    .filter((timestamp) => now - timestamp < GUEST_WINDOW_MS);

  if (recentRequests.length >= limit) {
    guestRequests.set(bucketKey, recentRequests);
    return false;
  }

  recentRequests.push(now);
  guestRequests.set(bucketKey, recentRequests);
  if (guestRequests.size > 10_000) {
    for (const [ip, timestamps] of guestRequests) {
      if (!timestamps.some((timestamp) => now - timestamp < GUEST_WINDOW_MS)) {
        guestRequests.delete(ip);
      }
      if (guestRequests.size <= 10_000) break;
    }
  }
  return true;
}

function describeQuote(quote: MarketQuote): string {
  const number = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 });
  const asOf = quote.asOf
    ? new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "short",
      timeStyle: "short",
      timeZone: "Asia/Ho_Chi_Minh",
    }).format(quote.asOf)
    : "không rõ thời điểm";
  const change = quote.change === null
    ? "chưa có dữ liệu so sánh phiên trước"
    : `${quote.change > 0 ? "+" : ""}${number.format(quote.change)} ${
      quote.changePercent === null
        ? ""
        : `(${quote.changePercent > 0 ? "+" : ""}${number.format(quote.changePercent)}%)`
    } so với phiên trước`;

  return `${quote.symbol} (${quote.name}): giá gần nhất ${number.format(quote.price)} ${quote.currency}; thay đổi ${change}; khối lượng ${
    quote.volume === null ? "chưa có dữ liệu" : number.format(quote.volume)
  }; thời điểm dữ liệu ${asOf}. Nguồn: ${quote.source}.`;
}

async function callGroq(question: string, apiKey: string, marketContext?: string) {
  const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: Deno.env.get("GROQ_MODEL") ?? "llama-3.3-70b-versatile",
      messages: [
        { role: "system", content: systemPrompt },
        {
          role: "user",
          content: marketContext ? `${question}\n\n${marketContext}` : question,
        },
      ],
      temperature: 0.2,
      max_tokens: 900,
    }),
    signal: AbortSignal.timeout(25_000),
  });

  if (!response.ok) {
    console.error(`Groq request failed with status ${response.status}`);
    return null;
  }

  const payload = await response.json();
  const answer = payload.choices?.[0]?.message?.content;
  return typeof answer === "string" && answer.trim()
    ? { answer: answer.trim(), provider: "groq" }
    : null;
}

async function callCloudflareAI(question: string, marketContext?: string) {
  const endpoint = Deno.env.get("CF_AI_PROXY_URL");
  const secret = Deno.env.get("CF_AI_PROXY_SECRET");
  if (!endpoint || !secret) {
    console.error("Cloudflare Workers AI proxy configuration is missing.");
    return null;
  }

  let url: URL;
  try {
    url = new URL(endpoint);
  } catch {
    console.error("Cloudflare Workers AI proxy URL is invalid.");
    return null;
  }
  if (url.protocol !== "https:" || url.pathname !== "/internal/ai") {
    console.error("Cloudflare Workers AI proxy URL must be HTTPS and end at /internal/ai.");
    return null;
  }

  const body = JSON.stringify({
    messages: [
      { role: "system", content: systemPrompt },
      {
        role: "user",
        content: marketContext ? `${question}\n\n${marketContext}` : question,
      },
    ],
  });
  const timestamp = Date.now().toString();
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = new Uint8Array(
    await crypto.subtle.sign(
      "HMAC",
      key,
      new TextEncoder().encode(`${timestamp}.${body}`),
    ),
  );
  const signatureHex = Array.from(signature, (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Findata-Timestamp": timestamp,
      "X-Findata-Signature": signatureHex,
    },
    body,
    signal: AbortSignal.timeout(35_000),
  });

  if (!response.ok) {
    console.error(`Cloudflare Workers AI request failed with status ${response.status}`);
    return null;
  }

  const payload = await response.json();
  return typeof payload.answer === "string" && payload.answer.trim()
    ? {
      answer: payload.answer.trim(),
      provider: "Cloudflare Workers AI · Qwen3 30B",
    }
    : null;
}

async function callGemini(question: string, apiKey: string, marketContext?: string) {
  const model = Deno.env.get("GEMINI_MODEL") ?? "gemini-2.5-flash";
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": apiKey,
      },
      body: JSON.stringify({
        systemInstruction: { parts: [{ text: systemPrompt }] },
        contents: [{
          role: "user",
          parts: [{
            text: marketContext ? `${question}\n\n${marketContext}` : question,
          }],
        }],
        generationConfig: { temperature: 0.2, maxOutputTokens: 900 },
      }),
      signal: AbortSignal.timeout(25_000),
    },
  );

  if (!response.ok) {
    console.error(`Gemini request failed with status ${response.status}`);
    return null;
  }

  const payload = await response.json();
  const answer = payload.candidates?.[0]?.content?.parts
    ?.map((part: { text?: string }) => part.text ?? "")
    .join("")
    .trim();
  return typeof answer === "string" && answer
    ? { answer, provider: "gemini" }
    : null;
}

async function generateAnswer(question: string, marketContext?: string) {
  try {
    const result = await callCloudflareAI(question, marketContext);
    if (result) return result;
  } catch (error) {
    console.error(
      error instanceof Error
        ? `Cloudflare Workers AI request failed: ${error.message}`
        : "Cloudflare Workers AI request failed",
    );
  }

  const groqKey = Deno.env.get("GROQ_API_KEY");
  if (groqKey) {
    try {
      const result = await callGroq(question, groqKey, marketContext);
      if (result) return result;
    } catch (error) {
      console.error(
        error instanceof Error ? `Groq request failed: ${error.message}` : "Groq request failed",
      );
    }
  }

  const geminiKey = Deno.env.get("GEMINI_API_KEY");
  if (geminiKey) {
    try {
      const result = await callGemini(question, geminiKey, marketContext);
      if (result) return result;
    } catch (error) {
      console.error(
        error instanceof Error ? `Gemini request failed: ${error.message}` : "Gemini request failed",
      );
    }
  }

  return null;
}

export default {
  fetch: withSupabase({ auth: ["user", "none"] }, async (request, ctx) => {
    if (request.method !== "POST") {
      return json({ error: "Phương thức không được hỗ trợ." }, 405);
    }

    let payload: unknown;
    try {
      payload = await request.json();
    } catch {
      return json({ error: "Yêu cầu phải là JSON hợp lệ." }, 400);
    }
    if (
      typeof payload !== "object" ||
      payload === null ||
      Array.isArray(payload)
    ) {
      return json({ error: "Nội dung yêu cầu phải là một object JSON." }, 400);
    }
    const body = payload as {
      action?: unknown;
      question?: unknown;
      sessionId?: unknown;
      symbol?: unknown;
      range?: unknown;
    };

    const userId = ctx.authMode === "user" ? ctx.userClaims?.id ?? null : null;

    if (body.action === "sessions") {
      if (!userId) {
        return json({ error: "Đăng nhập để đồng bộ các phiên trò chuyện." }, 401);
      }
      const { data, error } = await ctx.supabase
        .from("chat_sessions")
        .select("id, title, created_at, updated_at")
        .eq("user_id", userId)
        .order("updated_at", { ascending: false })
        .limit(100);
      if (error) {
        console.error(`Chat sessions read failed: ${error.code ?? "unknown"}`);
        return json({ error: "Không thể tải danh sách phiên trò chuyện." }, 500);
      }
      return json({ sessions: data ?? [] });
    }

    if (body.action === "create-session") {
      if (!userId) {
        return json({ error: "Đăng nhập để đồng bộ các phiên trò chuyện." }, 401);
      }
      const { data, error } = await ctx.supabase
        .from("chat_sessions")
        .insert({ user_id: userId })
        .select("id, title, created_at, updated_at")
        .single();
      if (error || !data) {
        console.error(`Chat session creation failed: ${error?.code ?? "unknown"}`);
        return json({ error: "Không thể tạo phiên trò chuyện mới." }, 500);
      }
      return json({ session: data });
    }

    if (body.action === "delete-session") {
      if (!userId) {
        return json({ error: "Đăng nhập để quản lý phiên trò chuyện." }, 401);
      }
      if (
        typeof body.sessionId !== "string" ||
        !/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i
          .test(body.sessionId)
      ) {
        return json({ error: "Mã phiên trò chuyện không hợp lệ." }, 400);
      }
      const { data, error } = await ctx.supabase
        .from("chat_sessions")
        .delete()
        .eq("id", body.sessionId)
        .eq("user_id", userId)
        .select("id")
        .maybeSingle();
      if (error) {
        console.error(`Chat session deletion failed: ${error.code ?? "unknown"}`);
        return json({ error: "Không thể xóa phiên trò chuyện." }, 500);
      }
      if (!data) {
        return json({ error: "Không tìm thấy phiên trò chuyện." }, 404);
      }
      return json({ deleted: data.id });
    }

    if (body.action === "history") {
      if (!userId) {
        return json({ error: "Đăng nhập để xem lịch sử trò chuyện." }, 401);
      }
      if (
        typeof body.sessionId !== "string" ||
        !/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i
          .test(body.sessionId)
      ) {
        return json({ error: "Mã phiên trò chuyện không hợp lệ." }, 400);
      }
      const { data, error } = await ctx.supabase
        .from("chat_messages")
        .select("id, role, content, metadata, created_at")
        .eq("user_id", userId)
        .eq("session_id", body.sessionId)
        .order("created_at", { ascending: false })
        .limit(200);
      if (error) {
        console.error(`Chat history read failed: ${error.code ?? "unknown"}`);
        return json({ error: "Không thể tải lịch sử trò chuyện." }, 500);
      }
      return json({ messages: (data ?? []).reverse() });
    }

    if (body.action === "chart") {
      if (
        typeof body.symbol !== "string" ||
        !supportedSymbols.includes(body.symbol)
      ) {
        return json({ error: "Mã cổ phiếu chưa có trong danh sách hỗ trợ." }, 400);
      }
      if (
        typeof body.range !== "string" ||
        !Object.hasOwn(chartPeriods, body.range)
      ) {
        return json({ error: "Khoảng thời gian biểu đồ không hợp lệ." }, 400);
      }
      if (!allowGuestRequest(request, 15)) {
        return json(
          { error: "Bạn đã xem quá nhiều biểu đồ. Vui lòng thử lại sau một phút." },
          429,
        );
      }
      try {
        const range = body.range as keyof typeof chartPeriods;
        const history = await fetchHistoricalChart(body.symbol, range);
        const first = history.points[0];
        const latest = history.points.at(-1)!;
        const changePercent = first.close
          ? ((latest.close - first.close) / first.close) * 100
          : null;
        return json({
          symbol: body.symbol,
          name: history.name,
          currency: history.currency,
          range,
          rangeLabel: chartPeriods[range].label,
          points: history.points,
          periodChangePercent: changePercent,
          asOf: latest.timestamp,
          source: "Yahoo Finance",
          sourceUrl: `https://finance.yahoo.com/quote/${body.symbol}.VN/history/`,
        });
      } catch (error) {
        console.error(
          error instanceof Error
            ? `Historical chart request failed for ${body.symbol}: ${error.message}`
            : `Historical chart request failed for ${body.symbol}`,
        );
        return json(
          { error: "Không tải được lịch sử giá từ nguồn dữ liệu. Hãy thử lại sau." },
          502,
        );
      }
    }

    if (body.action === "market") {
      try {
        const snapshot = await getMarketSnapshot();
        return json({
          ...snapshot,
          source: "Yahoo Finance",
          refreshedAt: Date.now(),
        });
      } catch (error) {
        console.error(
          error instanceof Error ? error.message : "Market data request failed",
        );
        return json({ error: "Nguồn dữ liệu thị trường hiện không phản hồi." }, 502);
      }
    }

    if (body.action !== "ask") {
      return json({ error: "Thao tác không được hỗ trợ." }, 400);
    }
    if (typeof body.question !== "string") {
      return json({ error: "Câu hỏi phải là chuỗi văn bản." }, 400);
    }

    const question = body.question.trim();
    if (!question || question.length > 2000) {
      return json({ error: "Câu hỏi phải có từ 1 đến 2000 ký tự." }, 400);
    }

    if (
      typeof body.sessionId !== "string" ||
      !/^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i
        .test(body.sessionId)
    ) {
      return json({ error: "Mã phiên trò chuyện không hợp lệ." }, 400);
    }
    const sessionId = body.sessionId;
    let currentSessionTitle: string | null = null;
    if (userId) {
      const { data: session, error: sessionError } = await ctx.supabase
        .from("chat_sessions")
        .select("id, title")
        .eq("id", sessionId)
        .eq("user_id", userId)
        .maybeSingle();
      if (sessionError) {
        console.error(`Chat session check failed: ${sessionError.code ?? "unknown"}`);
        return json({ error: "Không thể xác minh phiên trò chuyện." }, 500);
      }
      if (!session) {
        return json({ error: "Phiên trò chuyện không tồn tại hoặc không thuộc tài khoản." }, 404);
      }
      currentSessionTitle = session.title;
    }

    if (userId) {
      const cutoff = new Date(Date.now() - 60_000).toISOString();
      const { count, error: rateError } = await ctx.supabase
        .from("chat_messages")
        .select("id", { count: "exact", head: true })
        .eq("user_id", userId)
        .eq("role", "user")
        .gte("created_at", cutoff);
      if (rateError) {
        console.error(`Rate limit lookup failed: ${rateError.code ?? "unknown"}`);
        return json({ error: "Không thể kiểm tra giới hạn truy vấn." }, 500);
      }
      if ((count ?? 0) >= 10) {
        return json(
          { error: "Bạn đã đạt giới hạn 10 câu hỏi mỗi phút. Hãy thử lại sau." },
          429,
        );
      }
    } else if (!allowGuestRequest(request)) {
      return json(
        { error: "Phiên khách đã đạt giới hạn 5 câu hỏi mỗi phút. Hãy thử lại sau." },
        429,
      );
    }

    try {
      const insertMessage = async (
        role: "user" | "assistant",
        content: string,
        metadata: Record<string, string>,
      ) => {
        const { error } = await ctx.supabase.from("chat_messages").insert({
          user_id: userId,
          session_id: sessionId,
          role,
          content,
          metadata,
        });
        if (error) {
          console.error(`Chat history insert failed: ${error.code ?? "unknown"}`);
          throw new Error("Không thể lưu lịch sử trò chuyện.");
        }
      };
      if (userId) {
        await insertMessage("user", question, {});
        const normalizedTitle = Array.from(question.replace(/\s+/g, " ").trim())
          .slice(0, 75)
          .join("");
        const { error: updateError } = await ctx.supabase
          .from("chat_sessions")
          .update({
            title: currentSessionTitle === "Cuộc trò chuyện mới"
              ? normalizedTitle
              : currentSessionTitle,
            updated_at: new Date().toISOString(),
          })
          .eq("id", sessionId)
          .eq("user_id", userId);
        if (updateError) {
          console.error(`Chat session update failed: ${updateError.code ?? "unknown"}`);
          return json({ error: "Không thể cập nhật phiên trò chuyện." }, 500);
        }
      }

      let result: { answer: string; provider: string; chart?: MarketChart };
      let intent: string;
      let citations: { title: string; url: string }[] = [];
      if (requiresMarketData(question)) {
        const symbol = getQuestionSymbol(question);
        if (!symbol) {
          intent = "market_data_unavailable";
          result = {
            provider: "none",
            answer: "Findata hiện hỗ trợ giá tham khảo cho các mã trong bảng theo dõi. Để xem lịch sử giá, mở mục “Diễn biến giá” và chọn mã cùng khoảng thời gian; trợ lý chat chưa phân tích chuỗi lịch sử. P/E, báo cáo doanh nghiệp và dữ liệu vĩ mô chưa được kết nối.",
          };
        } else if (!isQuoteOnlyQuestion(question)) {
          intent = "market_data_unavailable";
          result = {
            provider: "none",
            answer: `Bạn có thể xem lịch sử giá ${symbol} tại mục “Diễn biến giá” bằng cách chọn mã và khoảng thời gian. Trợ lý chat hiện chỉ xác nhận giá gần nhất, biến động so với phiên trước và khối lượng tham khảo; chưa phân tích chuỗi lịch sử. P/E, P/B, báo cáo doanh nghiệp và định giá chưa được kết nối nên mình không thể xác nhận các số liệu đó.`,
          };
        } else {
          try {
            const snapshot = await getMarketSnapshot();
            const quote = snapshot.quotes.find((item) => item.symbol === symbol);
            if (!quote) {
              return json(
                { error: `Nguồn dữ liệu hiện không có báo giá cho ${symbol}.` },
                503,
              );
            }
            const marketContext = describeQuote(quote);
            citations = [{ title: "Yahoo Finance", url: quote.sourceUrl }];
            if (/giá|thị giá|bao nhiêu/i.test(question)) {
              result = { answer: marketContext, provider: "market_data" };
            } else {
              const generated = await generateAnswer(question, marketContext);
              if (!generated) {
                return json(
                  { error: "Dịch vụ AI hiện chưa sẵn sàng. Vui lòng thử lại sau." },
                  503,
                );
              }
              result = generated;
            }
            intent = "market_quote";
            if (/biểu đồ|vẽ|đồ thị|chart/i.test(question)) {
              if (quote.previousClose === null) {
                result.answer +=
                  "\n\nChưa thể vẽ biểu đồ so sánh vì nguồn hiện chưa cung cấp giá phiên trước.";
              } else {
                result.chart = {
                  title: `${quote.symbol} · so sánh giá tham chiếu`,
                  labels: ["Phiên trước", "Gần nhất"],
                  values: [quote.previousClose, quote.price],
                  unit: quote.currency,
                  source: quote.source,
                  asOf: quote.asOf,
                };
              }
            }
          } catch (error) {
            console.error(
              error instanceof Error ? error.message : "Market quote unavailable",
            );
            result = {
              provider: "none",
              answer: `Hiện chưa nhận được báo giá xác thực cho ${symbol}. Mình sẽ không tự điền số liệu; bạn có thể thử lại sau.`,
            };
            intent = "market_data_unavailable";
          }
        }
      } else {
        const generated = await generateAnswer(question);
        if (!generated) {
          return json(
            { error: "Dịch vụ AI hiện chưa sẵn sàng. Vui lòng thử lại sau." },
            503,
          );
        }
        intent = "concept_explanation";
        result = generated;
      }

      if (userId) {
        await insertMessage("assistant", result.answer, {
          intent,
          provider: result.provider,
          ...(result.chart ? { chart: JSON.stringify(result.chart) } : {}),
          ...(citations.length
            ? { citations: JSON.stringify(citations) }
            : {}),
        });
      }

      return json({
        answer: result.answer,
        intent,
        provider: result.provider,
        citations,
        chart: result.chart ?? null,
      });
    } catch (error) {
      console.error(
        error instanceof Error ? error.message : "Unknown chat request failure",
      );
      return json({ error: "Không thể hoàn tất yêu cầu trò chuyện." }, 500);
    }
  }),
};
