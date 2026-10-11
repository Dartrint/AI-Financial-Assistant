import { withSupabase } from "npm:@supabase/server@1";

const supportedSymbols = [
  "VCB", "BID", "CTG", "VNM", "FPT", "VIC", "MSN", "VJC",
  "SAB", "HPG", "MWG", "VRE", "HDB", "TCB", "VPB",
];

const systemPrompt = [
  "Bạn là trợ lý giáo dục tài chính, trả lời bằng tiếng Việt rõ ràng và ngắn gọn.",
  "Giải thích khái niệm, công thức và phương pháp phân tích chung.",
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

let marketCache: { expiresAt: number; quotes: MarketQuote[]; unavailableSymbols: string[] } | null = null;
let marketRequest: Promise<{ quotes: MarketQuote[]; unavailableSymbols: string[] }> | null = null;
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
    (asksForMetric && asksForPeriod);
}

function isQuoteOnlyQuestion(question: string): boolean {
  return /giá|thị giá|đóng cửa|tăng|giảm|biến động|khối lượng|volume|cao nhất|thấp nhất/i
    .test(question.normalize("NFC")) &&
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

function allowGuestRequest(request: Request): boolean {
  const forwardedFor = request.headers.get("x-forwarded-for");
  const clientIp = request.headers.get("cf-connecting-ip") ??
    forwardedFor?.split(",")[0]?.trim() ??
    "unknown";
  const now = Date.now();
  const recentRequests = (guestRequests.get(clientIp) ?? [])
    .filter((timestamp) => now - timestamp < GUEST_WINDOW_MS);

  if (recentRequests.length >= GUEST_REQUEST_LIMIT) {
    guestRequests.set(clientIp, recentRequests);
    return false;
  }

  recentRequests.push(now);
  guestRequests.set(clientIp, recentRequests);
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
    const body = payload as { action?: unknown; question?: unknown };

    const userId = ctx.authMode === "user" ? ctx.userClaims?.id ?? null : null;

    if (body.action === "history") {
      if (!userId) {
        return json({ error: "Đăng nhập để xem lịch sử trò chuyện." }, 401);
      }
      const { data, error } = await ctx.supabase
        .from("chat_messages")
        .select("id, role, content, metadata, created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(100);
      if (error) {
        console.error(`Chat history read failed: ${error.code ?? "unknown"}`);
        return json({ error: "Không thể tải lịch sử trò chuyện." }, 500);
      }
      return json({ messages: (data ?? []).reverse() });
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
          role,
          content,
          metadata,
        });
        if (error) {
          console.error(`Chat history insert failed: ${error.code ?? "unknown"}`);
          throw new Error("Không thể lưu lịch sử trò chuyện.");
        }
      };
      if (userId) await insertMessage("user", question, {});

      let result: { answer: string; provider: string };
      let intent: string;
      let citations: { title: string; url: string }[] = [];
      if (requiresMarketData(question)) {
        const symbol = getQuestionSymbol(question);
        if (!symbol) {
          intent = "market_data_unavailable";
          result = {
            provider: "none",
            answer: "Phiên bản giới thiệu hiện hỗ trợ dữ liệu giá tham khảo cho các mã trong bảng theo dõi. Vui lòng chọn một mã đang hiển thị; P/E, báo cáo tài chính và các mã khác chưa được kết nối.",
          };
        } else if (!isQuoteOnlyQuestion(question)) {
          intent = "market_data_unavailable";
          result = {
            provider: "none",
            answer: `Hiện Findata chỉ có giá, biến động phiên và khối lượng tham khảo của ${symbol}. P/E, P/B, báo cáo doanh nghiệp và định giá chưa được kết nối nên mình không thể xác nhận số liệu đó.`,
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
        });
      }

      return json({
        answer: result.answer,
        intent,
        provider: result.provider,
        citations,
      });
    } catch (error) {
      console.error(
        error instanceof Error ? error.message : "Unknown chat request failure",
      );
      return json({ error: "Không thể hoàn tất yêu cầu trò chuyện." }, 500);
    }
  }),
};
