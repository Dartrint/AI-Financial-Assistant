import { createClient } from "@supabase/supabase-js";
import "./style.css";

const elements = {
  accountStatus: document.querySelector("#account-status"),
  authForm: document.querySelector("#auth-form"),
  authMessage: document.querySelector("#auth-message"),
  authPanel: document.querySelector("#auth-panel"),
  authSubmit: document.querySelector("#auth-submit"),
  chatForm: document.querySelector("#chat-form"),
  chatPanel: document.querySelector("#chat-panel"),
  conversation: document.querySelector("#conversation"),
  email: document.querySelector("#email"),
  question: document.querySelector("#question"),
  sendButton: document.querySelector("#send-button"),
  signOut: document.querySelector("#sign-out"),
  tickerList: document.querySelector("#ticker-list"),
  toast: document.querySelector("#toast"),
};

const tickers = ["VCB", "BID", "CTG", "VNM", "FPT", "VIC", "MSN", "VJC", "SAB", "HPG", "MWG", "VRE", "HDB", "TCB", "VPB"];
let supabase;
let toastTimeout;

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
  elements.authPanel.hidden = signedIn;
  elements.chatPanel.hidden = !signedIn;
  elements.accountStatus.textContent = signedIn
    ? session.user.email ?? "ĐÃ ĐĂNG NHẬP"
    : "CHƯA ĐĂNG NHẬP";
  if (signedIn) {
    setTimeout(() => loadHistory(), 0);
  } else {
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
      "Không thể hoàn tất yêu cầu. Câu hỏi đã được giữ trong lịch sử; vui lòng thử lại sau.",
    );
  } finally {
    setBusy(elements.sendButton, false, "Đang trả lời…", "Gửi câu hỏi");
    elements.question.focus();
  }
}

function initializeTickers() {
  const fragment = document.createDocumentFragment();
  for (const symbol of tickers) {
    const item = document.createElement("span");
    item.className = "ticker";
    item.textContent = symbol;
    item.title = "Nguồn dữ liệu thị trường chưa được kết nối";
    fragment.append(item);
  }
  elements.tickerList.append(fragment);
}

async function initializeApp() {
  initializeTickers();
  try {
    await import(/* @vite-ignore */ "/config.js");
  } catch (error) {
    console.error("Unable to load public Supabase configuration.", error);
    elements.accountStatus.textContent = "THIẾU CẤU HÌNH";
    setAuthMessage("Không thể tải cấu hình Supabase.", true);
    elements.authPanel.hidden = false;
    return;
  }
  const config = window.FINDATA_CONFIG;
  if (!config?.supabaseUrl || !config?.supabasePublishableKey) {
    elements.accountStatus.textContent = "THIẾU CẤU HÌNH";
    setAuthMessage("Thiếu cấu hình Supabase cho giao diện.", true);
    elements.authPanel.hidden = false;
    return;
  }

  supabase = createClient(config.supabaseUrl, config.supabasePublishableKey);

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
}

initializeApp();
