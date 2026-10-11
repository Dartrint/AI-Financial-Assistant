import { createClient } from "@supabase/supabase-js";
import "./style.css";

const elements = {
  accountStatus: document.querySelector("#account-status"),
  authForm: document.querySelector("#auth-form"),
  authMessage: document.querySelector("#auth-message"),
  authPanel: document.querySelector("#auth-panel"),
  authSubmit: document.querySelector("#auth-submit"),
  authToggle: document.querySelector("#auth-toggle"),
  chatForm: document.querySelector("#chat-form"),
  chatPanel: document.querySelector("#chat-panel"),
  marketQuotes: document.querySelector("#market-quotes"),
  marketUpdated: document.querySelector("#market-updated"),
  refreshMarket: document.querySelector("#refresh-market"),
  conversation: document.querySelector("#conversation"),
  email: document.querySelector("#email"),
  question: document.querySelector("#question"),
  sendButton: document.querySelector("#send-button"),
  signOut: document.querySelector("#sign-out"),
  toast: document.querySelector("#toast"),
};

const tickers = ["VCB", "BID", "CTG", "VNM", "FPT", "VIC", "MSN", "VJC", "SAB", "HPG", "MWG", "VRE", "HDB", "TCB", "VPB"];
let supabase;
let toastTimeout;
let authPanelOpen = false;
let activeUserId;

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => elements.toast.classList.remove("visible"), 4500);
}

function setAuthMessage(message, isError = false) {
  elements.authMessage.textContent = message;
  elements.authMessage.classList.toggle("error", isError);
}

function setBusy(button, busy, busyText, idleText) {
  button.disabled = busy;
  button.querySelector("span").textContent = busy ? busyText : idleText;
}

function renderMessage(role, content, metadata = {}) {
  document.querySelector("#welcome")?.remove();

  const article = document.createElement("article");
  article.className = `message ${role}`;
  const badge = document.createElement("span");
  badge.className = "message-badge";
  badge.textContent = role === "user" ? "BẠN" : "FINDATA";

  const body = document.createElement("div");
  body.className = "message-body";
  const text = document.createElement("p");
  text.textContent = content;
  body.append(text);

  if (metadata.provider || metadata.intent) {
    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = [metadata.intent, metadata.provider].filter(Boolean).join(" · ");
    body.append(meta);
  }

  article.append(badge, body);
  elements.conversation.append(article);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function renderHistory(messages) {
  elements.conversation.replaceChildren();
  if (!messages.length) {
    elements.conversation.innerHTML = `
      <div id="welcome" class="welcome">
        <span class="welcome-mark">F</span>
        <h3>Bạn muốn tìm hiểu điều gì?</h3>
        <p>Câu trả lời được tạo bởi AI và không thay thế tư vấn đầu tư.</p>
        <div class="suggestions">
          <button class="suggestion" type="button" data-question="ROE là gì và được tính như thế nào?">ROE là gì?</button>
          <button class="suggestion" type="button" data-question="Giải thích sự khác nhau giữa P/E và P/B.">P/E và P/B</button>
          <button class="suggestion" type="button" data-question="Nhà đầu tư nên đọc báo cáo lưu chuyển tiền tệ như thế nào?">Đọc báo cáo lưu chuyển tiền tệ</button>
        </div>
      </div>`;
    return;
  }

  for (const message of messages) {
    renderMessage(message.role, message.content, message.metadata ?? {});
  }
}

function formatNumber(value, options = {}) {
  return new Intl.NumberFormat("vi-VN", options).format(value);
}

function formatMarketTime(timestamp) {
  if (!timestamp) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Ho_Chi_Minh",
  }).format(new Date(timestamp));
}

function renderMarketQuotes(quotes, unavailableSymbols = []) {
  const quoteBySymbol = new Map(quotes.map((quote) => [quote.symbol, quote]));
  const unavailable = new Set(unavailableSymbols);
  const fragment = document.createDocumentFragment();

  for (const symbol of tickers) {
    const quote = quoteBySymbol.get(symbol);
    const row = document.createElement("tr");
    const symbolCell = document.createElement("th");
    symbolCell.scope = "row";
    symbolCell.textContent = symbol;
    row.append(symbolCell);

    if (!quote) {
      const unavailableCell = document.createElement("td");
      unavailableCell.colSpan = 4;
      unavailableCell.className = "quote-unavailable";
      unavailableCell.textContent = unavailable.has(symbol)
        ? "Nguồn dữ liệu tạm thời không có mã này"
        : "Chưa có dữ liệu";
      row.append(unavailableCell);
      fragment.append(row);
      continue;
    }

    const priceCell = document.createElement("td");
    priceCell.className = "quote-price";
    priceCell.textContent = `${formatNumber(quote.price, { maximumFractionDigits: 2 })} ₫`;

    const changeCell = document.createElement("td");
    const changePercent = quote.changePercent;
    changeCell.className = `quote-change ${changePercent > 0 ? "positive" : changePercent < 0 ? "negative" : ""}`;
    const changeSign = quote.change > 0 ? "+" : "";
    changeCell.textContent = quote.change == null || changePercent == null
      ? "—"
      : `${changeSign}${formatNumber(quote.change, { maximumFractionDigits: 2 })} (${changeSign}${formatNumber(changePercent, { maximumFractionDigits: 2 })}%)`;

    const volumeCell = document.createElement("td");
    volumeCell.textContent = quote.volume == null
      ? "—"
      : formatNumber(quote.volume, { maximumFractionDigits: 0 });

    const timeCell = document.createElement("td");
    timeCell.className = "quote-time";
    timeCell.textContent = formatMarketTime(quote.asOf);

    row.append(priceCell, changeCell, volumeCell, timeCell);
    fragment.append(row);
  }

  elements.marketQuotes.replaceChildren(fragment);
  const latestTimestamp = Math.max(
    0,
    ...quotes.map((quote) => quote.asOf ?? 0),
  );
  elements.marketUpdated.textContent = quotes.length
    ? `${quotes.length}/${tickers.length} mã · dữ liệu gần nhất ${formatMarketTime(latestTimestamp)}`
    : "Chưa nhận được dữ liệu thị trường.";
}

async function invoke(action, values = {}) {
  const { data, error } = await supabase.functions.invoke("financial-assistant", {
    body: { action, ...values },
  });
  if (error) {
    throw new Error(error.message || "Không thể kết nối Supabase.");
  }
  if (data?.error) {
    throw new Error(data.error);
  }
  return data;
}

async function loadMarketData() {
  elements.refreshMarket.disabled = true;
  elements.refreshMarket.textContent = "Đang tải…";
  elements.marketUpdated.textContent = "Đang cập nhật dữ liệu từ Yahoo Finance…";

  try {
    const result = await invoke("market");
    renderMarketQuotes(result.quotes ?? [], result.unavailableSymbols ?? []);
  } catch (error) {
    elements.marketUpdated.textContent = "Không thể tải bảng giá.";
    elements.marketQuotes.innerHTML =
      '<tr><td colspan="5" class="table-message">Nguồn dữ liệu đang gặp sự cố. Hãy thử làm mới sau.</td></tr>';
    showToast(error.message);
  } finally {
    elements.refreshMarket.disabled = false;
    elements.refreshMarket.textContent = "Làm mới";
  }
}

async function loadHistory() {
  try {
    const data = await invoke("history");
    renderHistory(data.messages ?? []);
  } catch (error) {
    showToast(error.message);
  }
}

function showSignedIn(session) {
  const signedIn = Boolean(session?.user);
  const userId = signedIn ? session.user.id : null;
  elements.chatPanel.hidden = false;
  elements.authPanel.hidden = signedIn || !authPanelOpen;
  elements.authToggle.hidden = signedIn;
  elements.signOut.hidden = !signedIn;
  elements.authToggle.setAttribute("aria-expanded", String(!elements.authPanel.hidden));
  elements.accountStatus.textContent = signedIn
    ? session.user.email ?? "ĐÃ ĐĂNG NHẬP"
    : "DÙNG THỬ · KHÔNG CẦN ĐĂNG NHẬP";
  document.querySelector("#chat-subtitle").textContent = signedIn
    ? "Lịch sử trò chuyện được lưu riêng trong tài khoản của bạn."
    : "Phiên khách · Hội thoại không được lưu sau khi đóng trang.";

  if (userId && userId !== activeUserId) {
    activeUserId = userId;
    setTimeout(() => loadHistory(), 0);
  } else if (!userId && activeUserId) {
    activeUserId = null;
    renderHistory([]);
  }
}

async function sendQuestion(question) {
  if (!question.trim()) return;

  renderMessage("user", question);
  elements.question.value = "";
  setBusy(elements.sendButton, true, "Đang trả lời…", "Gửi câu hỏi");

  try {
    const result = await invoke("ask", { question });
    renderMessage("assistant", result.answer, {
      intent: result.intent,
      provider: result.provider,
    });
  } catch (error) {
    showToast(error.message);
    renderMessage(
      "assistant",
      "Không thể hoàn tất yêu cầu. Vui lòng thử lại sau.",
    );
  } finally {
    setBusy(elements.sendButton, false, "Đang trả lời…", "Gửi câu hỏi");
    elements.question.focus();
  }
}

async function initializeApp() {
  try {
    await import(/* @vite-ignore */ "/config.js");
  } catch (error) {
    console.error("Unable to load public Supabase configuration.", error);
    elements.accountStatus.textContent = "THIẾU CẤU HÌNH";
    setAuthMessage("Không thể tải cấu hình Supabase.", true);
    elements.authPanel.hidden = false;
    elements.chatPanel.hidden = false;
    return;
  }
  const config = window.FINDATA_CONFIG;
  if (!config?.supabaseUrl || !config?.supabasePublishableKey) {
    elements.accountStatus.textContent = "THIẾU CẤU HÌNH";
    setAuthMessage("Thiếu cấu hình Supabase cho giao diện.", true);
    elements.authPanel.hidden = false;
    elements.chatPanel.hidden = false;
    return;
  }

  supabase = createClient(config.supabaseUrl, config.supabasePublishableKey);

  elements.authToggle.addEventListener("click", () => {
    authPanelOpen = !authPanelOpen;
    elements.authPanel.hidden = !authPanelOpen;
    elements.authToggle.setAttribute("aria-expanded", String(authPanelOpen));
    if (authPanelOpen) elements.email.focus();
  });

  elements.authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = elements.email.value.trim();
    elements.authSubmit.disabled = true;
    setAuthMessage("");
    try {
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: window.location.origin },
      });
      if (error) throw error;
      setAuthMessage("Đã gửi liên kết đăng nhập. Hãy kiểm tra hộp thư của bạn.");
    } catch (error) {
      setAuthMessage(error.message || "Không thể gửi email đăng nhập.", true);
    } finally {
      elements.authSubmit.disabled = false;
    }
  });

  elements.chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendQuestion(elements.question.value);
  });

  elements.question.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      elements.chatForm.requestSubmit();
    }
  });

  document.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => {
      elements.question.value = button.dataset.question;
      elements.question.focus();
    });
  });

  elements.signOut.addEventListener("click", async () => {
    const { error } = await supabase.auth.signOut();
    if (error) showToast(error.message);
  });

  elements.refreshMarket.addEventListener("click", loadMarketData);
  supabase.auth.onAuthStateChange((event, session) => {
    showSignedIn(session);
    if (event === "SIGNED_IN") setAuthMessage("");
  });
  supabase.auth.getSession().then(({ data, error }) => {
    if (error) {
      showToast(error.message);
      return;
    }
    showSignedIn(data.session);
  });
  await loadMarketData();
}

initializeApp();
