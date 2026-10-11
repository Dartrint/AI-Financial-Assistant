import { withSupabase } from "npm:@supabase/server@1";

const supportedSymbols = [
  "VCB", "BID", "CTG", "VNM", "FPT", "VIC", "MSN", "VJC",
  "SAB", "HPG", "MWG", "VRE", "HDB", "TCB", "VPB",
];

const systemPrompt = [
  "Bạn là trợ lý giáo dục tài chính, trả lời bằng tiếng Việt rõ ràng và ngắn gọn.",
  "Chỉ giải thích khái niệm, công thức và phương pháp phân tích chung.",
  "Bạn không có quyền truy cập dữ liệu thị trường hoặc báo cáo doanh nghiệp trực tiếp.",
  "Không bịa số liệu, giá cổ phiếu, ngày tháng, nguồn trích dẫn hoặc hiệu suất đầu tư.",
  "Không đưa ra khuyến nghị mua, bán hay lời khuyên đầu tư cá nhân hóa.",
  "Nếu câu hỏi yêu cầu dữ liệu mới nhất, hãy nói rõ nguồn dữ liệu chưa được kết nối.",
].join(" ");

const json = (payload: unknown, status = 200) =>
  Response.json(payload, { status });

function requiresMarketData(question: string): boolean {
  const normalized = question.normalize("NFC");
  const hasTicker = new RegExp(
    `\\b(?:${supportedSymbols.join("|")})\\b`,
    "i",
  ).test(normalized);
  const asksForMetric =
    /giá|thị giá|p\s*\/\s*e|p\s*\/\s*b|doanh thu|lợi nhuận|cổ tức|vốn hóa|roe|roa|eps|báo cáo tài chính|lưu chuyển tiền/i
      .test(normalized);
  const asksForPeriod =
    /hiện tại|hôm nay|mới nhất|gần nhất|bao nhiêu|năm\s*20\d{2}|quý\s*[1-4]|20\d{2}/i
      .test(normalized);

  return (hasTicker && asksForMetric) || (asksForMetric && asksForPeriod);
}

async function callGroq(question: string, apiKey: string) {
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
        { role: "user", content: question },
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

async function callGemini(question: string, apiKey: string) {
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
        contents: [{ role: "user", parts: [{ text: question }] }],
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

async function generateAnswer(question: string) {
  const groqKey = Deno.env.get("GROQ_API_KEY");
  if (groqKey) {
    try {
      const result = await callGroq(question, groqKey);
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
      const result = await callGemini(question, geminiKey);
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
  fetch: withSupabase({ auth: "user" }, async (request, ctx) => {
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

    const { data: userData, error: userError } = await ctx.supabase.auth.getUser();
    const userId = userData.user?.id;
    if (userError || !userId) {
      return json({ error: "Phiên đăng nhập không hợp lệ." }, 401);
    }

    if (body.action === "history") {
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
      await insertMessage("user", question, {});

      let result: { answer: string; provider: string };
      let intent: string;
      if (requiresMarketData(question)) {
        intent = "market_data_unavailable";
        result = {
          provider: "none",
          answer:
            "Nguồn dữ liệu giá và báo cáo tài chính chưa được kết nối với phiên bản này. Để tránh cung cấp số liệu sai, mình chưa thể trả lời truy vấn cụ thể đó. Hiện bạn có thể hỏi về khái niệm hoặc phương pháp phân tích tài chính.",
        };
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

      await insertMessage("assistant", result.answer, {
        intent,
        provider: result.provider,
      });

      return json({
        answer: result.answer,
        intent,
        provider: result.provider,
        citations: [],
      });
    } catch (error) {
      console.error(
        error instanceof Error ? error.message : "Unknown chat request failure",
      );
      return json({ error: "Không thể hoàn tất yêu cầu trò chuyện." }, 500);
    }
  }),
};
