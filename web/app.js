import {
  elapsedLabel,
  filterAvailableRooms,
  formatJstDateTime,
  parseHistory,
  summarizeTypes,
  validateLatest,
  validateRoomConfig,
} from "./data-utils.js?v=4.2.1";
import { FACILITY_KEYS, FACILITY_META } from "./facility-meta.js?v=4.2.1";
import {
  ALL_DAY_HOURS,
  EVENING_TIME_SLOTS,
  HOUR_MS,
  WEEKDAY_LABELS,
  analyzeAvailability,
  filterHistoryByRollingHours,
} from "./analytics-utils.js?v=4.2.1";

const FEATURED_ROOMS = ["611", "612", "615"];
const DATA_URLS = {
  latest: "./data/latest.json",
  history: "./data/history.csv",
  rooms: "./config/rooms.json",
};

const state = {
  activeView: "now",
  latest: null,
  masterRooms: [],
  history: [],
  historyLoaded: false,
  historyLoading: false,
  historyRequest: null,
  historyError: null,
  loading: false,
  activeFacility: null,
  analysisHours: 168,
  analysis: null,
  timeViewMode: "evening",
  rankingFacility: null,
  rankingExpanded: false,
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

function createFacilityChips(facilities) {
  const list = document.createElement("div");
  list.className = "facility-chips";
  list.setAttribute("aria-label", "客室設備");
  for (const key of FACILITY_KEYS.filter((facility) => facilities.includes(facility))) {
    const meta = FACILITY_META[key];
    const chip = document.createElement("span");
    chip.className = "facility-chip";
    chip.innerHTML = `<span aria-hidden="true">${meta.icon}</span><span>${meta.label}</span>`;
    list.append(chip);
  }
  return list;
}

function facilityAriaText(facilities) {
  return FACILITY_KEYS
    .filter((facility) => facilities.includes(facility))
    .map((facility) => FACILITY_META[facility].label)
    .join("、");
}

function renderFeaturedRooms() {
  const masterByRoom = new Map(state.masterRooms.map((room) => [room.room, room]));
  const available = new Set(state.latest.available_rooms);
  element("featured-rooms").replaceChildren(...FEATURED_ROOMS.map((roomNumber) => {
    const room = masterByRoom.get(roomNumber);
    const isAvailable = available.has(roomNumber);
    const card = document.createElement("article");
    card.className = `featured-card ${isAvailable ? "available" : "not-available"}`;
    const facilities = room?.facilities || [];
    card.setAttribute(
      "aria-label",
      `Room ${roomNumber} Type ${room?.type || "不明"}。設備 ${facilityAriaText(facilities) || "比較設備なし"}。${isAvailable ? "空室あり" : "現在空室表示なし"}`,
    );
    card.innerHTML = `<strong class="room-number">${roomNumber}</strong><span class="room-type">Type ${room?.type || "--"}</span>`;
    card.append(createFacilityChips(facilities));
    const status = document.createElement("span");
    status.className = "state-badge";
    status.textContent = isAvailable ? "AVAILABLE" : "NOT AVAILABLE";
    card.append(status);
    return card;
  }));
}

function renderFacilityFilters() {
  const container = element("facility-filters");
  const options = [
    { key: null, label: "すべて", icon: null },
    ...FACILITY_KEYS.map((key) => ({ key, ...FACILITY_META[key] })),
  ];
  container.replaceChildren(...options.map(({ key, label, icon }) => {
    const button = document.createElement("button");
    const isActive = state.activeFacility === key;
    button.type = "button";
    button.className = `facility-filter${isActive ? " active" : ""}`;
    button.dataset.facility = key || "all";
    button.setAttribute("aria-pressed", String(isActive));
    button.setAttribute("aria-label", key ? `${label}付きの空室で絞り込む` : "すべての空室を表示");
    if (icon) {
      const symbol = document.createElement("span");
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = icon;
      button.append(symbol);
    }
    button.append(document.createTextNode(label));
    button.addEventListener("click", () => {
      state.activeFacility = key;
      renderFacilityFilters();
      renderAvailableRooms();
    });
    return button;
  }));
}

function renderAvailableRooms() {
  const available = filterAvailableRooms(
    state.latest.rooms,
    state.masterRooms,
    state.activeFacility,
  );
  element("room-count-pill").textContent = `${available.length}室`;
  const filterLabel = state.activeFacility ? FACILITY_META[state.activeFacility].label : "すべて";
  element("filter-result-summary").textContent = `${filterLabel}：${available.length}室`;
  const container = element("available-rooms");
  if (available.length === 0) {
    const message = state.activeFacility
      ? `現在、${FACILITY_META[state.activeFacility].label}付きの空室はありません。`
      : "現在、公式ページに空室表示はありません。";
    renderEmpty(container, message);
    return;
  }
  container.replaceChildren(...available.map((room) => {
    const card = document.createElement("article");
    card.className = "room-card available";
    card.setAttribute(
      "aria-label",
      `Room ${room.room} Type ${room.type}。設備 ${facilityAriaText(room.facilities) || "比較設備なし"}`,
    );
    const header = document.createElement("div");
    header.className = "room-card-header";
    header.innerHTML = `<strong class="room-number">${room.room}</strong><span class="room-type">Type ${room.type}</span>`;
    card.append(header, createFacilityChips(room.facilities));
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

function shortJstDateTime(value) {
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

function renderAvailabilityChart(recent, now) {
  const container = element("availability-chart");
  const startMs = now.getTime() - 24 * HOUR_MS;
  const endMs = now.getTime();
  element("recent-range").textContent = `${shortJstDateTime(startMs)} 〜 ${shortJstDateTime(endMs)}`;
  if (recent.length === 0) {
    renderEmpty(container, "直近24時間の観測データはありません。欠損時間を0室としては扱いません。");
    return;
  }

  const width = 680;
  const height = 250;
  const padding = { top: 24, right: 18, bottom: 38, left: 38 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const maximum = Math.max(5, Math.ceil(Math.max(...recent.map((entry) => entry.availableCount)) / 5) * 5);
  const x = (entry) => padding.left + ((new Date(entry.observedAt).getTime() - startMs) / (endMs - startMs)) * innerWidth;
  const y = (value) => padding.top + innerHeight - (value / maximum) * innerHeight;
  const svg = svgElement("svg", {
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": `直近24時間の空室数推移、${recent.length}観測`,
  });
  const title = svgElement("title");
  title.textContent = "直近24時間の空室数推移";
  svg.append(title);

  for (const value of [maximum, Math.round(maximum / 2), 0]) {
    const lineY = y(value);
    svg.append(svgElement("line", { x1: padding.left, y1: lineY, x2: width - padding.right, y2: lineY, class: "chart-grid-line" }));
    const label = svgElement("text", { x: padding.left - 9, y: lineY + 4, class: "chart-axis-label", "text-anchor": "end" });
    label.textContent = value;
    svg.append(label);
  }

  const points = recent.map((entry) => `${x(entry)},${y(entry.availableCount)}`).join(" ");
  if (recent.length > 1) svg.append(svgElement("polyline", { points, class: "chart-line" }));
  recent.forEach((entry) => {
    const dot = svgElement("circle", { cx: x(entry), cy: y(entry.availableCount), r: 4.5, class: "chart-dot" });
    const dotTitle = svgElement("title");
    dotTitle.textContent = `${shortJstDateTime(entry.observedAt)} ${entry.availableCount}室`;
    dot.append(dotTitle);
    svg.append(dot);
  });

  [0, 0.5, 1].forEach((ratio) => {
    const timestamp = startMs + (endMs - startMs) * ratio;
    const label = svgElement("text", {
      x: padding.left + innerWidth * ratio,
      y: height - 12,
      class: "chart-time-label",
      "text-anchor": ratio === 0 ? "start" : ratio === 1 ? "end" : "middle",
    });
    label.textContent = shortJstDateTime(timestamp);
    svg.append(label);
  });

  container.replaceChildren(svg);
  const note = document.createElement("p");
  note.className = "data-note";
  note.textContent = recent.length === 1
    ? "観測点が1件のため、推移グラフはデータ蓄積中です。"
    : `観測 ${recent.length}件。日付を跨いだraw観測を時刻間隔どおりに表示しています。`;
  container.append(note);
}

function renderRecentActivity(now = new Date()) {
  const container = element("availability-chart");
  if (state.historyError) {
    renderEmpty(container, `履歴を表示できません。${state.historyError}`);
    return;
  }
  renderAvailabilityChart(filterHistoryByRollingHours(state.history, 24, now), now);
}

function formatDecimal(value, suffix = "") {
  return value === null ? "--" : `${value.toFixed(1)}${suffix}`;
}

function renderPeriodControls() {
  for (const button of element("analysis-period-tabs").querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(Number(button.dataset.hours) === state.analysisHours));
  }
}

function renderAnalysisSummary(analysis) {
  const items = [
    ["観測ログ", `${analysis.observationCount}件`],
    ["観測時間", `${analysis.bucketCount} / ${analysis.hours}時間`],
    ["カバレッジ", `${analysis.coverage.percentage.toFixed(1)}%`],
    ["データ", `${analysis.dayCount}日分`],
    ["平均空室", formatDecimal(analysis.averageAvailableCount, "室")],
  ];
  element("analysis-summary").replaceChildren(...items.map(([label, value]) => {
    const card = document.createElement("article");
    card.className = "summary-card";
    card.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    return card;
  }));
}

function heatLevel(value) {
  if (value === null) return "heat-empty";
  if (value < 2) return "heat-level-0";
  if (value < 4) return "heat-level-1";
  if (value < 6) return "heat-level-2";
  if (value < 8) return "heat-level-3";
  return "heat-level-4";
}

function renderTimeViewControls() {
  for (const button of element("time-view-tabs").querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.timeView === state.timeViewMode));
  }
}

function renderHeatmap(analysis) {
  const isEvening = state.timeViewMode === "evening";
  const columns = isEvening ? EVENING_TIME_SLOTS : ALL_DAY_HOURS;
  const cells = isEvening ? analysis.eveningTime : analysis.allDayTime;
  const cellMap = new Map(cells.map((cell) => [
    `${cell.weekdayIndex}:${isEvening ? cell.slotKey : cell.hour}`,
    cell,
  ]));
  const table = document.createElement("table");
  table.className = `heatmap-table ${isEvening ? "mode-evening" : "mode-all-day"}`;
  const caption = document.createElement("caption");
  caption.className = "visually-hidden";
  caption.textContent = `${state.analysisHours / 24}日間の時間帯別平均空室数`;
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  const corner = document.createElement("th");
  corner.scope = "col";
  corner.textContent = "曜日";
  headRow.append(corner);
  for (const column of columns) {
    const heading = document.createElement("th");
    heading.scope = "col";
    if (isEvening) {
      const [start, end] = column.label.split("–");
      heading.innerHTML = `<span>${start}</span><small>–${end}</small>`;
      heading.dataset.slot = column.key;
    } else {
      heading.textContent = String(column).padStart(2, "0");
      heading.dataset.hour = String(column);
    }
    headRow.append(heading);
  }
  head.append(headRow);
  const body = document.createElement("tbody");
  for (const [weekdayIndex, weekday] of WEEKDAY_LABELS.entries()) {
    const row = document.createElement("tr");
    const heading = document.createElement("th");
    heading.scope = "row";
    heading.textContent = weekday;
    row.append(heading);
    for (const column of columns) {
      const columnKey = isEvening ? column.key : column;
      const cellData = cellMap.get(`${weekdayIndex}:${columnKey}`);
      const cell = document.createElement("td");
      const isLowSample = cellData.bucketCount > 0 && cellData.bucketCount < 3;
      cell.className = `heatmap-cell ${heatLevel(cellData.averageAvailableCount)}${isLowSample ? " is-low-sample" : ""}`;
      cell.setAttribute(
        "aria-label",
        cellData.averageAvailableCount === null
          ? `${weekday}曜日 ${cellData.ariaLabel}、データなし、n=0`
          : `${weekday}曜日 ${cellData.ariaLabel}、平均空室${cellData.averageAvailableCount.toFixed(1)}室、n=${cellData.bucketCount}`,
      );
      cell.innerHTML = cellData.averageAvailableCount === null
        ? "<strong>--</strong><small>n=0</small>"
        : `<strong>${cellData.averageAvailableCount.toFixed(1)}</strong><small>n=${cellData.bucketCount}</small>`;
      row.append(cell);
    }
    body.append(row);
  }
  table.append(caption, head, body);
  const container = element("availability-heatmap");
  container.setAttribute(
    "aria-label",
    `${isEvening ? "18時から24時" : "全日"}の時間帯別平均空室数。横にスクロールできます`,
  );
  container.replaceChildren(table);
  element("heatmap-help").textContent = isEvening
    ? "18〜22時は1時間bucket、22〜24時は15分date-slotです。nは使用した日付別bucket数です。"
    : "00〜23時を1時間bucketで表示します。nは使用したdate-hour bucket数です。";
  if (!isEvening && window.matchMedia("(max-width: 520px)").matches) {
    requestAnimationFrame(() => {
      const hour18 = table.querySelector('thead th[data-hour="18"]');
      if (hour18) container.scrollLeft = Math.max(0, hour18.offsetLeft - 64);
    });
  }
}

function renderFacilityInsights(analysis) {
  element("facility-insights").replaceChildren(...analysis.facilityRates.map((item) => {
    const meta = FACILITY_META[item.facility];
    const card = document.createElement("article");
    card.className = "facility-insight-card";
    const rateText = item.rate === null ? "--" : `${(item.rate * 100).toFixed(1)}%`;
    card.setAttribute(
      "aria-label",
      `${meta.label}、空室あり率${rateText}、対象${item.targetRooms.length}室、観測時間${item.bucketCount}`,
    );
    card.innerHTML = `
      <header><span aria-hidden="true">${meta.icon}</span><strong>${meta.label}</strong></header>
      <p><span>空室あり率</span><b>${rateText}</b></p>
      <small>対象 ${item.targetRooms.length}室 · n=${item.bucketCount}時間</small>
    `;
    return card;
  }));
}

function renderRankingFilters() {
  const options = [
    { key: null, label: "すべて", icon: null },
    ...FACILITY_KEYS.map((key) => ({ key, ...FACILITY_META[key] })),
  ];
  element("ranking-filters").replaceChildren(...options.map(({ key, label, icon }) => {
    const button = document.createElement("button");
    const isActive = state.rankingFacility === key;
    button.type = "button";
    button.disabled = Boolean(state.historyError);
    button.className = `facility-filter${isActive ? " active" : ""}`;
    button.setAttribute("aria-pressed", String(isActive));
    button.setAttribute("aria-label", key ? `${label}付き客室のランキング` : "全客室のランキング");
    if (icon) {
      const symbol = document.createElement("span");
      symbol.setAttribute("aria-hidden", "true");
      symbol.textContent = icon;
      button.append(symbol);
    }
    button.append(document.createTextNode(label));
    button.addEventListener("click", () => {
      state.rankingFacility = key;
      state.rankingExpanded = false;
      renderRankingFilters();
      if (state.analysis) renderRoomRanking(state.analysis);
    });
    return button;
  }));
}

function renderRoomRanking(analysis) {
  const filtered = analysis.roomRates.filter(
    (room) => state.rankingFacility === null || room.facilities.includes(state.rankingFacility),
  );
  const label = state.rankingFacility ? FACILITY_META[state.rankingFacility].label : "すべて";
  element("ranking-count-note").textContent = `${label}：${filtered.length}室`;
  const list = element("room-ranking");
  if (analysis.bucketCount === 0) {
    const item = document.createElement("li");
    item.className = "empty-state";
    item.textContent = "選択期間に観測hour bucketがないため、ランキングを計算できません。";
    list.replaceChildren(item);
  } else {
    const visible = state.rankingExpanded || filtered.length <= 10 ? filtered : filtered.slice(0, 10);
    list.replaceChildren(...visible.map((room, index) => {
      const item = document.createElement("li");
      item.className = "ranking-row";
      const percentage = room.rate === null ? null : room.rate * 100;
      item.setAttribute(
        "aria-label",
        `${index + 1}位 ${room.room}号室 Type ${room.type} 空室表示率${percentage === null ? "データなし" : `${percentage.toFixed(1)}%`}`,
      );
      item.innerHTML = `
        <span class="rank-number">${index + 1}</span>
        <strong>${room.room}</strong>
        <span class="ranking-type">Type ${room.type}</span>
        <span class="ranking-rate">${percentage === null ? "--" : `${percentage.toFixed(1)}%`}</span>
        <i class="ranking-bar" aria-hidden="true"><b style="width:${percentage || 0}%"></b></i>
      `;
      return item;
    }));
  }
  const toggle = element("ranking-toggle");
  toggle.hidden = filtered.length <= 10 || analysis.bucketCount === 0;
  toggle.textContent = state.rankingExpanded ? "上位10室に戻す" : "すべて表示";
  toggle.setAttribute("aria-expanded", String(state.rankingExpanded));
}

function renderAnalytics(now = new Date()) {
  renderPeriodControls();
  renderTimeViewControls();
  renderRankingFilters();
  if (state.historyError) {
    state.analysis = null;
    element("analysis-data-note").textContent = "履歴データを読み込めないため分析を表示できません。";
    renderEmpty(element("analysis-summary"), state.historyError);
    renderEmpty(element("availability-heatmap"), state.historyError);
    renderEmpty(element("facility-insights"), state.historyError);
    element("room-ranking").replaceChildren();
    element("ranking-toggle").hidden = true;
    return;
  }
  const analysis = analyzeAvailability(
    state.history,
    state.masterRooms,
    state.analysisHours,
    now,
  );
  state.analysis = analysis;
  const periodDays = state.analysisHours / 24;
  element("analysis-data-note").textContent = analysis.bucketCount < state.analysisHours
    ? `${periodDays}日windowのデータを収集中：観測${analysis.dayCount}日・${analysis.bucketCount}/${state.analysisHours}時間。未観測時間は統計から除外します。`
    : `${periodDays}日分の完了済みhour bucketを集計しています。`;
  renderAnalysisSummary(analysis);
  renderHeatmap(analysis);
  renderFacilityInsights(analysis);
  renderRoomRanking(analysis);
}

function renderHistory(now = new Date()) {
  element("history-state").hidden = true;
  element("trends-content").hidden = false;
  element("trends-panel").setAttribute("aria-busy", "false");
  renderRecentActivity(now);
  renderAnalytics(now);
}

function renderCurrentData() {
  renderHeader();
  renderFeaturedRooms();
  renderFacilityFilters();
  renderAvailableRooms();
  renderTypeSummary();
}

function renderHistoryLoading() {
  const target = element("history-state");
  target.className = "history-state loading";
  target.textContent = "履歴データを読み込んでいます…";
  target.hidden = false;
  element("trends-content").hidden = true;
  element("trends-panel").setAttribute("aria-busy", "true");
}

function renderHistoryError() {
  const target = element("history-state");
  target.className = "history-state error";
  const message = document.createElement("p");
  message.textContent = `履歴データを読み込めませんでした。${state.historyError}`;
  const retry = document.createElement("button");
  retry.type = "button";
  retry.textContent = "再読み込み";
  retry.addEventListener("click", () => ensureHistoryLoaded({ force: true }));
  target.replaceChildren(message, retry);
  target.hidden = false;
  element("trends-content").hidden = true;
  element("trends-panel").setAttribute("aria-busy", "false");
}

async function ensureHistoryLoaded({ force = false } = {}) {
  if (state.historyLoading) return state.historyRequest;
  if (state.historyLoaded && !force) {
    if (state.historyError) renderHistoryError();
    else renderHistory();
    return true;
  }

  state.historyLoading = true;
  state.historyError = null;
  renderHistoryLoading();
  state.historyRequest = (async () => {
    try {
      const history = parseHistory(await fetchFresh(DATA_URLS.history, "text"));
      state.history = history;
      state.historyLoaded = true;
      state.historyError = null;
      renderHistory();
      return true;
    } catch (error) {
      console.error(error);
      state.historyError = error.message;
      if (!state.historyLoaded) state.history = [];
      renderHistoryError();
      return false;
    } finally {
      state.historyLoading = false;
      state.historyRequest = null;
      element("trends-panel").setAttribute("aria-busy", "false");
    }
  })();
  return state.historyRequest;
}

function activateView(view, { focus = false } = {}) {
  if (!["now", "trends"].includes(view)) return;
  const previousView = state.activeView;
  state.activeView = view;
  for (const tab of element("view-tabs").querySelectorAll('[role="tab"]')) {
    const selected = tab.dataset.view === view;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  }
  for (const panel of document.querySelectorAll('.view-panel[role="tabpanel"]')) {
    const active = panel.id === `${view}-panel`;
    panel.hidden = !active;
    panel.classList.remove("slide-from-left", "slide-from-right");
    if (active && previousView !== view) {
      panel.classList.add(view === "trends" ? "slide-from-right" : "slide-from-left");
      panel.addEventListener(
        "animationend",
        () => panel.classList.remove("slide-from-left", "slide-from-right"),
        { once: true },
      );
    }
  }
  const tabsTop = element("view-tabs-shell").offsetTop;
  if (window.scrollY > tabsTop + 24) window.scrollTo({ top: tabsTop, behavior: "smooth" });
  if (view === "trends") ensureHistoryLoaded();
}

async function loadAllData() {
  if (state.loading) return;
  state.loading = true;
  element("refresh-button").disabled = true;
  element("view-trends-tab").disabled = true;
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
    renderCurrentData();
    if (state.historyLoaded) await ensureHistoryLoaded({ force: true });
    setStatus("");
  } catch (error) {
    console.error(error);
    setStatus(`データを表示できません。${error.message}`, true);
  } finally {
    state.loading = false;
    element("refresh-button").disabled = false;
    element("view-trends-tab").disabled = !state.latest || state.masterRooms.length === 0;
  }
}

async function pollLatest() {
  if (state.loading || !state.latest || state.masterRooms.length === 0) return;
  try {
    const next = validateLatest(await fetchFresh(DATA_URLS.latest), state.masterRooms);
    if (next.observed_at !== state.latest.observed_at) {
      state.latest = next;
      renderCurrentData();
      if (state.historyLoaded) await ensureHistoryLoaded({ force: true });
      setStatus("新しい観測データに更新しました。");
      setTimeout(() => setStatus(""), 3500);
    } else if (state.historyLoaded && state.activeView === "trends") {
      renderHistory();
    }
  } catch (error) {
    console.error(error);
    setStatus(`自動更新に失敗しました。${error.message}`, true);
  }
}

element("refresh-button").addEventListener("click", loadAllData);
element("view-tabs").addEventListener("click", (event) => {
  const tab = event.target.closest('[role="tab"][data-view]');
  if (tab) activateView(tab.dataset.view);
});
element("view-tabs").addEventListener("keydown", (event) => {
  const tabs = [...element("view-tabs").querySelectorAll('[role="tab"]')]
    .filter((tab) => !tab.disabled);
  const currentIndex = tabs.indexOf(event.target);
  if (currentIndex < 0) return;
  let nextIndex = currentIndex;
  if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
  else if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
  else if (event.key === "Home") nextIndex = 0;
  else if (event.key === "End") nextIndex = tabs.length - 1;
  else return;
  event.preventDefault();
  activateView(tabs[nextIndex].dataset.view, { focus: true });
});
element("analysis-period-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-hours]");
  if (!button) return;
  state.analysisHours = Number(button.dataset.hours);
  state.rankingExpanded = false;
  renderAnalytics();
});
element("time-view-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-time-view]");
  if (!button) return;
  state.timeViewMode = button.dataset.timeView;
  renderTimeViewControls();
  renderHeatmap(state.analysis);
});
element("ranking-toggle").addEventListener("click", () => {
  state.rankingExpanded = !state.rankingExpanded;
  renderRoomRanking(state.analysis);
});
setInterval(() => {
  if (state.latest) element("elapsed-time").textContent = elapsedLabel(state.latest.observed_at);
}, 60000);
setInterval(pollLatest, 300000);

loadAllData();
