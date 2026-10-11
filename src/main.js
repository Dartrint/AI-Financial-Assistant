import { createClient } from "@supabase/supabase-js";
import DOMPurify from "dompurify";
import { marked } from "marked";
import "./style.css";

marked.setOptions({ gfm: true, breaks: true });

const markdownOptions = {
  ALLOWED_TAGS: [
    "a", "blockquote", "br", "code", "del", "em", "h1", "h2", "h3",
    "h4", "hr", "li", "ol", "p", "pre", "strong", "table", "tbody",
    "td", "th", "thead", "tr", "ul",
  ],
  ALLOWED_ATTR: ["href", "title", "colspan", "rowspan"],
};

const elements = {
  accountStatus: document.querySelector("#account-status"),
  authForm: document.querySelector("#auth-form"),
  authMessage: document.querySelector("#auth-message"),
  authPanel: document.querySelector("#auth-panel"),
  authSubmit: document.querySelector("#auth-submit"),
  authToggle: document.querySelector("#auth-toggle"),
  chatForm: document.querySelector("#chat-form"),
  chatPanel: document.querySelector("#chat-panel"),
  chartStatus: document.querySelector("#chart-status"),
  chartSummary: document.querySelector("#chart-summary"),
  chartSymbol: document.querySelector("#chart-symbol"),
  historyChart: document.querySelector("#history-chart"),
  refreshChart: document.querySelector("#refresh-chart"),
  newSession: document.querySelector("#new-session"),
  sessionEmpty: document.querySelector("#session-empty"),
  sessionList: document.querySelector("#session-list"),
  sessionSearch: document.querySelector("#session-search"),
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
const guestStorageKey = "findata-guest-sessions-v1";
let supabase;
let toastTimeout;
let authPanelOpen = false;
let activeUserId;
let activeSessionId = null;
let sessions = [];
let guestSessions = [];
let chartRange = "3mo";
let chartRequestId = 0;
let authTransitionId = 0;
let sessionRequestId = 0;
let sessionInitializationInProgress = false;
let sending = false;

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
  if (role === "assistant") {
    const markdown = document.createElement("div");
    markdown.className = "markdown-body";
    markdown.innerHTML = DOMPurify.sanitize(
      marked.parse(content, { async: false }),
      markdownOptions,
    );
    for (const link of markdown.querySelectorAll("a")) {
      link.target = "_blank";
      link.rel = "noopener noreferrer";
    }
    body.append(markdown);
  } else {
    const text = document.createElement("p");
    text.className = "user-message-text";
    text.textContent = content;
    body.append(text);
  }

  if (metadata.provider || metadata.intent) {
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const intents = {
      concept_explanation: "Giải thích tài chính",
      market_quote: "Dữ liệu thị trường",
      market_data_unavailable: "Thiếu dữ liệu thị trường",
    };
    meta.textContent = [
      intents[metadata.intent] ?? metadata.intent,
      metadata.provider,
    ].filter(Boolean).join(" · ");
    body.append(meta);
  }

  let citations = metadata.citations ?? [];
  if (typeof citations === "string") {
    try {
      citations = JSON.parse(citations);
    } catch {
      citations = [];
    }
  }
  if (Array.isArray(citations) && citations.length) {
    const sourceList = document.createElement("div");
    sourceList.className = "message-citations";
    const label = document.createElement("span");
    label.textContent = "Nguồn";
    sourceList.append(label);
    for (const citation of citations) {
      if (typeof citation?.title !== "string" || typeof citation?.url !== "string") {
        continue;
      }
      let sourceUrl;
      try {
        sourceUrl = new URL(citation.url);
      } catch {
        continue;
      }
      if (sourceUrl.protocol !== "https:" || sourceUrl.hostname !== "finance.yahoo.com") continue;
      const link = document.createElement("a");
      link.href = sourceUrl.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = citation.title;
      sourceList.append(link);
    }
    if (sourceList.querySelector("a")) body.append(sourceList);
  }

  let chart = metadata.chart ?? null;
  if (typeof chart === "string") {
    try {
      chart = JSON.parse(chart);
    } catch {
      chart = null;
    }
  }
  if (
    role === "assistant" &&
    chart &&
    typeof chart.title === "string" &&
    Array.isArray(chart.labels) &&
    Array.isArray(chart.values) &&
    chart.labels.length === 2 &&
    chart.labels.every((label) => typeof label === "string" && label.length <= 40) &&
    chart.values.length === 2 &&
    chart.values.every((value) => Number.isFinite(value) && value >= 0) &&
    typeof chart.unit === "string" &&
    chart.unit.length <= 12
  ) {
    const figure = document.createElement("figure");
    figure.className = "message-chart";
    const heading = document.createElement("figcaption");
    heading.textContent = chart.title;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 720 146");
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      `${chart.title}: ${chart.labels[0]} ${chart.values[0]}, ${chart.labels[1]} ${chart.values[1]} ${chart.unit ?? ""}`,
    );
    const minimumValue = Math.min(...chart.values);
    const maximumValue = Math.max(...chart.values);
    const padding = Math.max(
      (maximumValue - minimumValue) * 0.25,
      maximumValue * 0.005,
      1,
    );
    const minimum = Math.max(0, minimumValue - padding);
    const maximum = maximumValue + padding;
    const plotTop = 18;
    const plotBottom = 102;
    const valueY = (value) =>
      plotTop + ((maximum - value) / (maximum - minimum)) * (plotBottom - plotTop);
    const points = chart.values.map((value, index) => ({
      x: index === 0 ? 220 : 500,
      y: valueY(value),
    }));
    for (let index = 0; index < 3; index += 1) {
      const y = plotTop + index * ((plotBottom - plotTop) / 2);
      const gridline = document.createElementNS("http://www.w3.org/2000/svg", "line");
      gridline.setAttribute("x1", "150");
      gridline.setAttribute("x2", "570");
      gridline.setAttribute("y1", String(y));
      gridline.setAttribute("y2", String(y));
      gridline.setAttribute("class", "chart-gridline");
      svg.append(gridline);
    }
    const trend = document.createElementNS("http://www.w3.org/2000/svg", "line");
    trend.setAttribute("x1", String(points[0].x));
    trend.setAttribute("y1", String(points[0].y));
    trend.setAttribute("x2", String(points[1].x));
    trend.setAttribute("y2", String(points[1].y));
    trend.setAttribute("class", "chart-trend");
    svg.append(trend);
    for (let index = 0; index < chart.values.length; index += 1) {
      const { x, y } = points[index];
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", String(x));
      label.setAttribute("y", String(Math.max(13, y - 12)));
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("class", "chart-label");
      label.textContent = `${formatNumber(chart.values[index], { maximumFractionDigits: 2 })} ${chart.unit}`;
      svg.append(label);

      const marker = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      marker.setAttribute("cx", String(x));
      marker.setAttribute("cy", String(y));
      marker.setAttribute("r", "5");
      marker.setAttribute("class", index === 0 ? "chart-marker-previous" : "chart-marker-latest");
      svg.append(marker);

      const period = document.createElementNS("http://www.w3.org/2000/svg", "text");
      period.setAttribute("x", String(x));
      period.setAttribute("y", "128");
      period.setAttribute("text-anchor", "middle");
      period.setAttribute("class", "chart-period");
      period.textContent = chart.labels[index];
      svg.append(period);
    }
    const note = document.createElement("p");
    note.className = "chart-note";
    note.textContent = `Hai mốc giá theo dữ liệu nguồn${chart.asOf ? ` · cập nhật ${formatMarketTime(chart.asOf)}` : ""}; không phải chuỗi lịch sử. Trục dọc được thu hẹp để thấy rõ chênh lệch.`;
    figure.append(heading, svg, note);
    article.append(badge, body, figure);
  } else {
    article.append(badge, body);
  }
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
    const metadata = { ...(message.metadata ?? {}) };
    for (const key of ["chart", "citations"]) {
      if (typeof metadata[key] === "string") {
        try {
          metadata[key] = JSON.parse(metadata[key]);
        } catch {
          metadata[key] = null;
        }
      }
    }
    renderMessage(message.role, message.content, metadata);
  }
}

function makeSession() {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: "Cuộc trò chuyện mới",
    created_at: now,
    updated_at: now,
    messages: [],
  };
}

function saveGuestSessions() {
  try {
    const retainedSessions = [...guestSessions]
      .sort((first, second) =>
        Date.parse(second.updated_at) - Date.parse(first.updated_at)
      )
      .slice(0, 50);
    let serialized = JSON.stringify(retainedSessions);
    let trimmed = retainedSessions.length < guestSessions.length;

    while (serialized.length > 1_500_000 && retainedSessions.length > 1) {
      retainedSessions.pop();
      serialized = JSON.stringify(retainedSessions);
      trimmed = true;
    }
    while (
      serialized.length > 1_500_000 &&
      retainedSessions[0].messages.length > 1
    ) {
      const messages = retainedSessions[0].messages;
      messages.splice(0, Math.ceil(messages.length / 2));
      serialized = JSON.stringify(retainedSessions);
      trimmed = true;
    }

    guestSessions.splice(0, guestSessions.length, ...retainedSessions);
    localStorage.setItem(guestStorageKey, serialized);
    if (trimmed) {
      showToast("Đã giữ các phiên gần đây để không vượt dung lượng lưu trên thiết bị.");
    }
  } catch (error) {
    console.error("Unable to save guest sessions on this device.", error);
    showToast("Không thể lưu phiên trên thiết bị này. Hãy kiểm tra dung lượng trình duyệt.");
  }
}

function readStoredValue(key) {
  try {
    return localStorage.getItem(key);
  } catch (error) {
    console.error("Unable to access the browser's local storage.", error);
    return null;
  }
}

function readGuestSessions() {
  try {
    const stored = JSON.parse(readStoredValue(guestStorageKey) ?? "[]");
    if (!Array.isArray(stored)) return [];
    return stored
      .filter((session) =>
        session &&
        typeof session.id === "string" &&
        /^[\da-f-]{36}$/i.test(session.id) &&
        typeof session.title === "string" &&
        Array.isArray(session.messages)
      )
      .map((session) => ({
        id: session.id,
        title: session.title.slice(0, 80) || "Cuộc trò chuyện mới",
        created_at: typeof session.created_at === "string"
          ? session.created_at
          : new Date().toISOString(),
        updated_at: typeof session.updated_at === "string"
          ? session.updated_at
          : new Date().toISOString(),
        messages: session.messages
          .filter((message) =>
            message &&
            (message.role === "user" || message.role === "assistant") &&
            typeof message.content === "string"
          )
          .slice(-200)
          .map((message) => ({
            role: message.role,
            content: message.content.slice(0, 20_000),
            metadata: message.metadata && typeof message.metadata === "object"
              ? message.metadata
              : {},
          })),
      }))
      .slice(0, 100);
  } catch (error) {
    console.error("Unable to read guest sessions from this device.", error);
    showToast("Không thể đọc lịch sử lưu trên thiết bị này.");
    return [];
  }
}

function renderSessions() {
  const query = elements.sessionSearch.value.trim().toLocaleLowerCase("vi");
  const filtered = [...sessions]
    .sort((first, second) =>
      Date.parse(second.updated_at) - Date.parse(first.updated_at)
    )
    .filter((session) => session.title.toLocaleLowerCase("vi").includes(query));
  const fragment = document.createDocumentFragment();
  const template = document.querySelector("#session-item-template");

  for (const session of filtered) {
    const item = template.content.firstElementChild.cloneNode(true);
    const select = item.querySelector(".session-select");
    const remove = item.querySelector(".session-remove");
    select.textContent = session.title || "Cuộc trò chuyện mới";
    select.setAttribute("aria-current", String(session.id === activeSessionId));
    select.addEventListener("click", () => void activateSession(session.id));
    remove.setAttribute("aria-label", `Xóa phiên ${session.title}`);
    remove.addEventListener("click", () => void deleteSession(session.id));
    fragment.append(item);
  }

  elements.sessionList.replaceChildren(fragment);
  const noMatches = query.length > 0 && filtered.length === 0;
  elements.sessionEmpty.hidden = filtered.length > 0;
  elements.sessionEmpty.textContent = noMatches
    ? "Không tìm thấy phiên phù hợp."
    : "Các câu hỏi của bạn sẽ được nhóm theo phiên tại đây.";
}

function currentSession() {
  return sessions.find((session) => session.id === activeSessionId) ?? null;
}

function storeActiveSessionId() {
  const key = activeUserId
    ? `findata-active-session:${activeUserId}`
    : "findata-active-guest-session";
  try {
    localStorage.setItem(key, activeSessionId ?? "");
  } catch (error) {
    console.error("Unable to remember the active chat session.", error);
  }
}

async function activateSession(sessionId) {
  const session = sessions.find((item) => item.id === sessionId);
  if (!session) return;
  const requestId = ++sessionRequestId;
  activeSessionId = session.id;
  storeActiveSessionId();
  renderSessions();

  if (activeUserId) {
    elements.conversation.setAttribute("aria-busy", "true");
    try {
      const result = await invoke("history", { sessionId });
      if (requestId !== sessionRequestId || activeSessionId !== sessionId) return;
      session.messages = result.messages ?? [];
      renderHistory(result.messages ?? []);
    } catch (error) {
      if (requestId === sessionRequestId) showToast(error.message);
    } finally {
      if (requestId === sessionRequestId) {
        elements.conversation.removeAttribute("aria-busy");
      }
    }
  } else {
    renderHistory(session.messages);
  }
}

async function createSession() {
  if (activeUserId) {
    const ownerId = activeUserId;
    const result = await invoke("create-session");
    if (activeUserId !== ownerId) return;
    sessions.unshift({ ...result.session, messages: [] });
  } else {
    sessions.unshift(makeSession());
    if (sessions.length > 100) sessions.length = 100;
    saveGuestSessions();
  }
  await activateSession(sessions[0].id);
  elements.question.focus();
}

async function deleteSession(sessionId) {
  const session = sessions.find((item) => item.id === sessionId);
  if (!session || !window.confirm(`Xóa phiên "${session.title}" và toàn bộ tin nhắn?`)) {
    return;
  }

  if (activeUserId) {
    const ownerId = activeUserId;
    try {
      await invoke("delete-session", { sessionId });
      if (activeUserId !== ownerId) return;
    } catch (error) {
      showToast(error.message);
      return;
    }
  }

  sessions = sessions.filter((item) => item.id !== sessionId);
  if (!activeUserId) {
    guestSessions = sessions;
    saveGuestSessions();
  }
  if (activeSessionId === sessionId) {
    activeSessionId = sessions[0]?.id ?? null;
    if (activeSessionId) {
      await activateSession(activeSessionId);
    } else {
      renderHistory([]);
      await createSession();
    }
  } else {
    renderSessions();
  }
}

function renderHistoricalChart(data) {
  const points = data.points.filter((point) =>
    Number.isFinite(point.timestamp) &&
    Number.isFinite(point.close) &&
    point.close >= 0
  );
  if (points.length < 2) {
    throw new Error("Nguồn dữ liệu chưa có đủ điểm giá để vẽ biểu đồ.");
  }

  const width = 800;
  const height = 300;
  const padding = { top: 18, right: 16, bottom: 38, left: 75 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = points.map((point) => point.close);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = maximum - minimum || Math.max(Math.abs(maximum) * 0.02, 1);
  const low = Math.max(0, minimum - spread * 0.08);
  const high = maximum + spread * 0.08;
  const firstTimestamp = points[0].timestamp;
  const lastTimestamp = points.at(-1).timestamp;
  const coordinates = points.map((point) => ({
    x: padding.left + ((point.timestamp - firstTimestamp) / (lastTimestamp - firstTimestamp || 1)) * plotWidth,
    y: padding.top + ((high - point.close) / (high - low)) * plotHeight,
  }));
  const trendUp = points.at(-1).close >= points[0].close;
  const lineColor = trendUp ? "var(--aqua)" : "#ff9188";
  const linePath = coordinates
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)},${point.y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L${coordinates.at(-1).x},${padding.top + plotHeight} L${coordinates[0].x},${padding.top + plotHeight} Z`;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("role", "img");
  svg.setAttribute(
    "aria-label",
    `${data.name} (${data.symbol}), lịch sử giá đóng cửa ${data.rangeLabel}, ${points.length} điểm dữ liệu`,
  );

  for (let index = 0; index < 4; index += 1) {
    const ratio = index / 3;
    const y = padding.top + ratio * plotHeight;
    const value = high - ratio * (high - low);
    const grid = document.createElementNS("http://www.w3.org/2000/svg", "line");
    grid.setAttribute("x1", String(padding.left));
    grid.setAttribute("x2", String(width - padding.right));
    grid.setAttribute("y1", String(y));
    grid.setAttribute("y2", String(y));
    grid.setAttribute("class", "history-gridline");
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", String(padding.left - 10));
    label.setAttribute("y", String(y + 4));
    label.setAttribute("text-anchor", "end");
    label.setAttribute("class", "history-axis-label");
    label.textContent = formatNumber(value, { maximumFractionDigits: 0 });
    svg.append(grid, label);
  }

  const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
  area.setAttribute("d", areaPath);
  area.setAttribute("class", "history-area");
  area.style.setProperty("--chart-line", lineColor);
  const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
  line.setAttribute("d", linePath);
  line.setAttribute("class", "history-line");
  line.style.setProperty("--chart-line", lineColor);
  svg.append(area, line);

  for (const index of [0, Math.floor((points.length - 1) / 2), points.length - 1]) {
    const point = points[index];
    const coordinate = coordinates[index];
    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", String(coordinate.x));
    label.setAttribute("y", String(height - 11));
    label.setAttribute("text-anchor", index === 0 ? "start" : index === points.length - 1 ? "end" : "middle");
    label.setAttribute("class", "history-axis-label");
    label.textContent = new Intl.DateTimeFormat("vi-VN", {
      month: "short",
      year: "2-digit",
      timeZone: "Asia/Ho_Chi_Minh",
    }).format(new Date(point.timestamp));
    svg.append(label);
  }

  const latest = points.at(-1);
  const start = points[0];
  const change = data.periodChangePercent;
  const changeText = Number.isFinite(change)
    ? `${change > 0 ? "+" : ""}${formatNumber(change, { maximumFractionDigits: 2 })}%`
    : "—";
  const volumeText = latest.volume == null
    ? ""
    : ` · KL phiên ${formatNumber(latest.volume, { maximumFractionDigits: 0 })}`;
  elements.chartSummary.textContent =
    `${data.name} (${data.symbol}) · ${formatNumber(latest.close, { maximumFractionDigits: 2 })} ${data.currency}` +
    ` · ${changeText} trong ${data.rangeLabel} · ${points.length} phiên${volumeText}`;
  elements.chartSummary.dataset.direction = change > 0 ? "up" : change < 0 ? "down" : "flat";
  elements.historyChart.replaceChildren(svg);
  elements.chartStatus.textContent =
    `Từ ${formatMarketTime(start.timestamp)} đến ${formatMarketTime(latest.timestamp)} · cập nhật ${formatMarketTime(data.asOf)} · Nguồn: Yahoo Finance`;
}

async function loadHistoricalChart() {
  const requestId = ++chartRequestId;
  const symbol = elements.chartSymbol.value;
  elements.refreshChart.disabled = true;
  elements.chartStatus.textContent = "Đang tải dữ liệu lịch sử giá…";
  elements.historyChart.setAttribute("aria-busy", "true");
  try {
  const data = await invoke("chart", { symbol, range: chartRange });
  if (requestId === chartRequestId) renderHistoricalChart(data);
  } catch (error) {
  if (requestId === chartRequestId) {
    elements.chartSummary.textContent = "Chưa thể hiển thị dữ liệu.";
    elements.chartStatus.textContent = error.message;
    elements.historyChart.replaceChildren();
    }
  } finally {
    if (requestId === chartRequestId) {
      elements.refreshChart.disabled = false;
      elements.historyChart.removeAttribute("aria-busy");
    }
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
    let message = "Không thể kết nối đến dịch vụ. Vui lòng thử lại sau.";
    if (error.context instanceof Response) {
      const body = await error.context.clone().json().catch(() => null);
      message = typeof body?.error === "string"
        ? body.error
        : "Dịch vụ chưa thể xử lý yêu cầu. Vui lòng thử lại sau.";
    }
    throw new Error(message);
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

async function showSignedIn(session) {
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
    ? "Phiên trò chuyện được đồng bộ riêng tư trong tài khoản của bạn."
    : "Phiên khách · Hội thoại được lưu cục bộ trên thiết bị này.";

  if (
    userId === activeUserId &&
    (activeSessionId || sessionInitializationInProgress)
  ) return;
  const transitionId = ++authTransitionId;
  activeUserId = userId;
  sessions = [];
  activeSessionId = null;

  if (userId) {
    sessionInitializationInProgress = true;
    try {
      const result = await invoke("sessions");
      if (transitionId !== authTransitionId) return;
      sessions = (result.sessions ?? []).map((item) => ({ ...item, messages: [] }));
      const rememberedId = readStoredValue(`findata-active-session:${userId}`);
      renderSessions();
      if (!sessions.length) {
        await createSession();
        return;
      }
      await activateSession(
        sessions.some((item) => item.id === rememberedId)
          ? rememberedId
          : sessions[0].id,
      );
    } catch (error) {
      if (transitionId === authTransitionId) showToast(error.message);
    } finally {
      if (transitionId === authTransitionId) {
        sessionInitializationInProgress = false;
      }
    }
    return;
  }

  guestSessions = readGuestSessions();
  sessions = guestSessions;
  const rememberedId = readStoredValue("findata-active-guest-session");
  if (!sessions.length) {
    sessions = [makeSession()];
    guestSessions = sessions;
  }
  if (!sessions.some((item) => item.id === rememberedId)) {
    activeSessionId = sessions[0].id;
  } else {
    activeSessionId = rememberedId;
  }
  saveGuestSessions();
  storeActiveSessionId();
  renderSessions();
  renderHistory(currentSession()?.messages ?? []);
}

async function sendQuestion(question) {
  if (sending || !question.trim()) return;

  if (!currentSession()) {
    try {
      await createSession();
    } catch (error) {
      showToast(error.message);
      return;
    }
  }
  const session = currentSession();
  if (!session) return;
  const requestUserId = activeUserId;
  const cleanQuestion = question.trim();
  const now = new Date().toISOString();
  session.messages ??= [];
  session.messages.push({
    role: "user",
    content: cleanQuestion,
    metadata: {},
    created_at: now,
  });
  if (session.messages.length > 200) {
    session.messages.splice(0, session.messages.length - 200);
  }
  if (session.title === "Cuộc trò chuyện mới") {
    session.title = Array.from(cleanQuestion.replace(/\s+/g, " "))
      .slice(0, 75)
      .join("");
  }
  session.updated_at = now;
  renderSessions();
  if (!activeUserId) saveGuestSessions();
  renderMessage("user", question);
  elements.question.value = "";
  sending = true;
  setBusy(elements.sendButton, true, "Đang trả lời…", "Gửi câu hỏi");

  try {
    const result = await invoke("ask", {
      question: cleanQuestion,
      sessionId: session.id,
    });
    const metadata = {
      intent: result.intent,
      provider: result.provider,
      citations: result.citations,
      chart: result.chart,
    };
    session.messages.push({
      role: "assistant",
      content: result.answer,
      metadata,
      created_at: new Date().toISOString(),
    });
    if (session.messages.length > 200) {
      session.messages.splice(0, session.messages.length - 200);
    }
    session.updated_at = new Date().toISOString();
    if (!requestUserId) saveGuestSessions();
    renderSessions();
    if (activeSessionId === session.id) {
      renderMessage("assistant", result.answer, {
        ...metadata,
      });
    }
  } catch (error) {
    showToast(error.message);
    if (activeSessionId === session.id) {
      renderMessage(
        "assistant",
        "Không thể hoàn tất yêu cầu. Vui lòng thử lại sau.",
      );
    }
  } finally {
    sending = false;
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

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-question]");
    if (!button) return;
    elements.question.value = button.dataset.question;
    elements.question.focus();
  });

  elements.newSession.addEventListener("click", async () => {
    try {
      await createSession();
    } catch (error) {
      showToast(error.message);
    }
  });
  elements.sessionSearch.addEventListener("input", renderSessions);
  elements.chartSymbol.addEventListener("change", loadHistoricalChart);
  elements.refreshChart.addEventListener("click", loadHistoricalChart);
  document.querySelectorAll("[data-chart-range]").forEach((button) => {
    button.addEventListener("click", () => {
      chartRange = button.dataset.chartRange;
      document.querySelectorAll("[data-chart-range]").forEach((tab) => {
        tab.setAttribute("aria-pressed", String(tab === button));
      });
      void loadHistoricalChart();
    });
  });

  elements.signOut.addEventListener("click", async () => {
    const { error } = await supabase.auth.signOut();
    if (error) showToast(error.message);
  });

  elements.refreshMarket.addEventListener("click", loadMarketData);
  supabase.auth.onAuthStateChange((event, session) => {
    void showSignedIn(session);
    if (event === "SIGNED_IN") setAuthMessage("");
  });
  supabase.auth.getSession().then(({ data, error }) => {
    if (error) {
      showToast(error.message);
      return;
    }
    void showSignedIn(data.session);
  });
  await Promise.all([loadMarketData(), loadHistoricalChart()]);
}

initializeApp();
