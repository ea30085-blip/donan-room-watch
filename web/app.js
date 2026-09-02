import {
  elapsedLabel,
  formatJstDateTime,
  parseHistory,
  roomTimeline,
  summarizeTypes,
  todaysHistory,
  tokyoTimeLabel,
  validateLatest,
  validateRoomConfig,
} from "./data-utils.js";

const FEATURED_ROOMS = ["611", "612", "615"];
const DATA_URLS = {
  latest: "./data/latest.json",
  history: "./data/history.csv",
  rooms: "./config/rooms.json",
};

const state = {
  latest: null,
  masterRooms: [],
  history: [],
  historyError: null,
  loading: false,
};

function element(id) {
  return document.getElementById(id);
}

async function fetchFresh(url, responseType = "json") {
  const separator = url.includes("?") ? "&" : "?";
  const response = await fetch(`${url}${separator}v=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url}を取得できません（HTTP ${response.status}）`);
  return responseType === "text" ? response.text() : response.json();
}

function setStatus(message = "", isError = false) {
  const target = element("status-message");
  target.textContent = message;
  target.classList.toggle("error", isError);
}

function renderEmpty(container, message) {
  const empty = document.createElement("p");
  empty.className = "empty-state";
  empty.textContent = message;
  container.replaceChildren(empty);
}

function renderHeader() {
  const { latest } = state;
  element("updated-at").dateTime = latest.observed_at;
  element("updated-at").textContent = formatJstDateTime(latest.observed_at);
  element("elapsed-time").textContent = elapsedLabel(latest.observed_at);
  element("available-count").textContent = latest.available_count;
  element("total-rooms").textContent = latest.total_rooms;
  element("preparing-count").textContent = latest.preparing_count;
  const rate = latest.total_rooms ? (latest.available_count / latest.total_rooms) * 100 : 0;
  element("availability-rate").textContent = `空室率 ${rate.toFixed(1)}%`;
}

function renderFeaturedRooms() {
  const masterByRoom = new Map(state.masterRooms.map((room) => [room.room, room]));
  const available = new Set(state.latest.available_rooms);
  element("featured-rooms").replaceChildren(...FEATURED_ROOMS.map((roomNumber) => {
    const room = masterByRoom.get(roomNumber);
    const isAvailable = available.has(roomNumber);
    const card = document.createElement("article");
    card.className = `featured-card ${isAvailable ? "available" : "not-available"}`;
    card.setAttribute("aria-label", `Room ${roomNumber} Type ${room?.type || "不明"} ${isAvailable ? "空室あり" : "現在空室表示なし"}`);
    card.innerHTML = `
      <strong class="room-number">${roomNumber}</strong>
      <span class="room-type">Type ${room?.type || "--"}</span>
      <span class="state-badge">${isAvailable ? "AVAILABLE" : "NOT AVAILABLE"}</span>
    `;
    return card;
  }));
}

function renderAvailableRooms() {
  const available = state.latest.rooms.filter((room) => room.status === "available");
  element("room-count-pill").textContent = `${available.length}室`;
  const container = element("available-rooms");
  if (available.length === 0) {
    renderEmpty(container, "現在、公式ページに空室表示はありません。");
    return;
  }
  container.replaceChildren(...available.map((room) => {
    const card = document.createElement("article");
    card.className = "room-card available";
    card.innerHTML = `<strong class="room-number">${room.room}</strong><span class="room-type">Type ${room.type}</span>`;
    return card;
  }));
}

function renderTypeSummary() {
  const summary = summarizeTypes(state.masterRooms, state.latest.available_rooms);
  element("type-summary").replaceChildren(...summary.map((item) => {
    const card = document.createElement("article");
    card.className = "type-card";
    const percentage = item.total ? (item.available / item.total) * 100 : 0;
    card.innerHTML = `
      <header><strong>Type ${item.type}</strong><span>${item.available} / ${item.total}</span></header>
      <div class="type-bar" aria-hidden="true"><i style="width: ${percentage}%"></i></div>
    `;
    return card;
  }));
}

function svgElement(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function renderAvailabilityChart(today) {
  const container = element("availability-chart");
  if (state.historyError) {
    renderEmpty(container, `履歴を表示できません。${state.historyError}`);
    return;
  }
  if (today.length === 0) {
    renderEmpty(container, "本日の観測データはまだありません。");
    return;
  }

  const width = 680;
  const height = 250;
  const padding = { top: 24, right: 18, bottom: 38, left: 38 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maximum = Math.max(5, Math.ceil(Math.max(...today.map((entry) => entry.availableCount)) / 5) * 5);
  const x = (index) => padding.left + (today.length === 1 ? innerWidth / 2 : (index / (today.length - 1)) * innerWidth);
  const y = (value) => padding.top + innerHeight - (value / maximum) * innerHeight;
  const svg = svgElement("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `本日の空室数推移、${today.length}観測`,
  });
  const title = svgElement("title");
  title.textContent = "本日の空室数推移";
  svg.append(title);

  for (const value of [maximum, Math.round(maximum / 2), 0]) {
    const lineY = y(value);
    svg.append(svgElement("line", { x1: padding.left, y1: lineY, x2: width - padding.right, y2: lineY, class: "chart-grid-line" }));
    const label = svgElement("text", { x: padding.left - 9, y: lineY + 4, class: "chart-axis-label", "text-anchor": "end" });
    label.textContent = value;
    svg.append(label);
  }

  const points = today.map((entry, index) => `${x(index)},${y(entry.availableCount)}`).join(" ");
  if (today.length > 1) svg.append(svgElement("polyline", { points, class: "chart-line" }));
  today.forEach((entry, index) => {
    const dot = svgElement("circle", { cx: x(index), cy: y(entry.availableCount), r: 4.5, class: "chart-dot" });
    const dotTitle = svgElement("title");
    dotTitle.textContent = `${tokyoTimeLabel(entry.observedAt)} ${entry.availableCount}室`;
    dot.append(dotTitle);
    svg.append(dot);
  });

  const labelIndexes = [...new Set([0, Math.floor((today.length - 1) / 2), today.length - 1])];
  labelIndexes.forEach((index) => {
    const label = svgElement("text", { x: x(index), y: height - 12, class: "chart-time-label", "text-anchor": index === 0 ? "start" : index === today.length - 1 ? "end" : "middle" });
    label.textContent = tokyoTimeLabel(today[index].observedAt);
    svg.append(label);
  });

  container.replaceChildren(svg);
  if (today.length === 1) {
    const note = document.createElement("p");
    note.className = "data-note";
    note.textContent = "観測点が1件のため、推移グラフはデータ蓄積中です。";
    container.append(note);
  }
}

function renderFeaturedTimeline(today) {
  const container = element("featured-timeline");
  if (state.historyError) {
    renderEmpty(container, `履歴を表示できません。${state.historyError}`);
    return;
  }
  if (today.length === 0) {
    renderEmpty(container, "本日の611 / 615の履歴はまだありません。");
    return;
  }

  const scroll = document.createElement("div");
  scroll.className = "timeline-scroll";
  scroll.tabIndex = 0;
  scroll.setAttribute("aria-label", "611号室と615号室の本日の状態推移。横にスクロールできます");
  const grid = document.createElement("div");
  grid.className = "timeline-grid";
  grid.style.setProperty("--timeline-count", today.length);

  const corner = document.createElement("div");
  corner.className = "timeline-corner";
  corner.textContent = "Room";
  grid.append(corner);
  today.forEach((entry) => {
    const time = document.createElement("time");
    time.className = "timeline-time";
    time.dateTime = entry.observedAt;
    time.textContent = tokyoTimeLabel(entry.observedAt);
    grid.append(time);
  });

  for (const roomNumber of ["611", "615"]) {
    const room = document.createElement("strong");
    room.className = "timeline-room";
    room.textContent = roomNumber;
    grid.append(room);
    roomTimeline(today, roomNumber).forEach((point) => {
      const status = document.createElement("div");
      status.className = `timeline-status ${point.available ? "available" : "not-available"}`;
      status.setAttribute("aria-label", `${roomNumber}号室 ${point.time} ${point.available ? "空室あり" : "現在空室表示なし"}`);
      status.innerHTML = `<i aria-hidden="true">${point.available ? "○" : "×"}</i><span>${point.available ? "空室" : "表示なし"}</span>`;
      grid.append(status);
    });
  }
  scroll.append(grid);
  container.replaceChildren(scroll);
}

function renderHistory() {
  const today = state.historyError ? [] : todaysHistory(state.history);
  renderAvailabilityChart(today);
  renderFeaturedTimeline(today);
}

function renderCurrentData() {
  renderHeader();
  renderFeaturedRooms();
  renderAvailableRooms();
  renderTypeSummary();
  renderHistory();
}

async function loadHistory() {
  try {
    state.history = parseHistory(await fetchFresh(DATA_URLS.history, "text"));
    state.historyError = null;
  } catch (error) {
    console.error(error);
    state.history = [];
    state.historyError = error.message;
  }
}

async function loadAllData() {
  if (state.loading) return;
  state.loading = true;
  element("refresh-button").disabled = true;
  setStatus("最新データを確認しています…");
  try {
    const [roomsDocument, latestDocument] = await Promise.all([
      fetchFresh(DATA_URLS.rooms),
      fetchFresh(DATA_URLS.latest),
    ]);
    const masterRooms = validateRoomConfig(roomsDocument);
    const latest = validateLatest(latestDocument, masterRooms);
    state.masterRooms = masterRooms;
    state.latest = latest;
    await loadHistory();
    renderCurrentData();
    setStatus(state.historyError ? "現在の空室は表示できましたが、履歴データを読み込めませんでした。" : "", Boolean(state.historyError));
  } catch (error) {
    console.error(error);
    setStatus(`データを表示できません。${error.message}`, true);
  } finally {
    state.loading = false;
    element("refresh-button").disabled = false;
  }
}

async function pollLatest() {
  if (state.loading || !state.latest || state.masterRooms.length === 0) return;
  try {
    const next = validateLatest(await fetchFresh(DATA_URLS.latest), state.masterRooms);
    if (next.observed_at !== state.latest.observed_at) {
      state.latest = next;
      await loadHistory();
      renderCurrentData();
      setStatus("新しい観測データに更新しました。");
      setTimeout(() => setStatus(""), 3500);
    }
  } catch (error) {
    console.error(error);
    setStatus(`自動更新に失敗しました。${error.message}`, true);
  }
}

element("refresh-button").addEventListener("click", loadAllData);
setInterval(() => {
  if (state.latest) element("elapsed-time").textContent = elapsedLabel(state.latest.observed_at);
}, 60000);
setInterval(pollLatest, 300000);

loadAllData();
