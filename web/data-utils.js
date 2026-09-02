const JST_TIME_ZONE = "Asia/Tokyo";

export function formatJstDateTime(isoString) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) {
    throw new Error(`Invalid observed_at: ${isoString}`);
  }
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: JST_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

export function elapsedLabel(isoString, now = new Date()) {
  const observed = new Date(isoString);
  if (Number.isNaN(observed.getTime())) return "時刻不明";
  const minutes = Math.max(0, Math.floor((now.getTime() - observed.getTime()) / 60000));
  if (minutes < 1) return "たった今";
  if (minutes < 60) return `${minutes}分前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}時間${minutes % 60}分前`;
  return `${Math.floor(hours / 24)}日前`;
}

export function validateRoomConfig(document) {
  if (!document || !Array.isArray(document.rooms) || document.rooms.length === 0) {
    throw new Error("rooms.jsonの客室マスタを読み込めません");
  }
  const seen = new Set();
  return document.rooms.map((entry) => {
    if (!entry || !/^[0-9]{3}$/.test(entry.room) || typeof entry.type !== "string" || !/^[A-I]$/.test(entry.type)) {
      throw new Error("rooms.jsonに不正な客室データがあります");
    }
    if (seen.has(entry.room)) throw new Error(`rooms.jsonに重複があります: ${entry.room}`);
    seen.add(entry.room);
    return { room: entry.room, type: entry.type };
  }).sort((a, b) => Number(a.room) - Number(b.room));
}

export function validateLatest(document, masterRooms) {
  if (!document || !Array.isArray(document.rooms) || !Array.isArray(document.available_rooms)) {
    throw new Error("latest.jsonの形式が不正です");
  }
  if (!Number.isInteger(document.available_count) || !Number.isInteger(document.total_rooms)) {
    throw new Error("latest.jsonの件数が不正です");
  }
  if (document.available_rooms.length !== document.available_count) {
    throw new Error("latest.jsonの空室件数が一致しません");
  }
  if (document.total_rooms !== masterRooms.length || document.rooms.length !== masterRooms.length) {
    throw new Error("latest.jsonの総客室数がマスタと一致しません");
  }
  const masterByRoom = new Map(masterRooms.map((entry) => [entry.room, entry.type]));
  const availableSet = new Set(document.available_rooms);
  if (availableSet.size !== document.available_rooms.length) {
    throw new Error("latest.jsonの空室番号に重複があります");
  }
  for (const entry of document.rooms) {
    if (!entry || masterByRoom.get(entry.room) !== entry.type) {
      throw new Error("latest.jsonの客室がマスタと一致しません");
    }
    const expectedStatus = availableSet.has(entry.room) ? "available" : "not_available";
    if (entry.status !== expectedStatus) {
      throw new Error(`latest.jsonの客室状態が一致しません: ${entry.room}`);
    }
  }
  formatJstDateTime(document.observed_at);
  return document;
}

export function summarizeTypes(masterRooms, availableRooms) {
  const availableSet = new Set(availableRooms);
  const summary = new Map();
  for (const { room, type } of masterRooms) {
    const current = summary.get(type) || { type, available: 0, total: 0 };
    current.total += 1;
    if (availableSet.has(room)) current.available += 1;
    summary.set(type, current);
  }
  return [...summary.values()].sort((a, b) => a.type.localeCompare(b.type));
}

export function parseCsv(text) {
  if (typeof text !== "string") throw new Error("CSVが文字列ではありません");
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
      continue;
    }
    if (character === '"' && field === "") {
      quoted = true;
    } else if (character === ",") {
      row.push(field);
      field = "";
    } else if (character === "\n" || character === "\r") {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(field);
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
      field = "";
    } else {
      field += character;
    }
  }
  if (quoted) throw new Error("history.csvの引用符が閉じられていません");
  if (field !== "" || row.length > 0) {
    row.push(field);
    if (row.some((value) => value !== "")) rows.push(row);
  }
  return rows;
}

function nonNegativeInteger(value, label) {
  if (!/^[0-9]+$/.test(value)) throw new Error(`history.csvの${label}が不正です`);
  return Number(value);
}

export function tokyoDateKey(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error(`不正な日時です: ${value}`);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: JST_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function tokyoTimeLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error(`不正な日時です: ${value}`);
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: JST_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

export function parseHistory(text) {
  const rows = parseCsv(text);
  const expectedHeader = [
    "observed_at",
    "available_count",
    "preparing_count",
    "total_rooms",
    "available_rooms",
  ];
  if (rows.length === 0 || rows[0].length !== expectedHeader.length || rows[0].some((value, index) => value !== expectedHeader[index])) {
    throw new Error("history.csvのヘッダーが不正です");
  }

  return rows.slice(1).map((values, index) => {
    if (values.length !== expectedHeader.length) {
      throw new Error(`history.csvの${index + 2}行目の列数が不正です`);
    }
    const observedAt = values[0];
    tokyoDateKey(observedAt);
    const availableRooms = values[4] === "" ? [] : values[4].split("|");
    if (availableRooms.some((room) => !/^[0-9]{3}$/.test(room)) || new Set(availableRooms).size !== availableRooms.length) {
      throw new Error(`history.csvの${index + 2}行目の空室番号が不正です`);
    }
    const availableCount = nonNegativeInteger(values[1], "available_count");
    if (availableRooms.length !== availableCount) {
      throw new Error(`history.csvの${index + 2}行目の空室件数が一致しません`);
    }
    return {
      observedAt,
      availableCount,
      preparingCount: nonNegativeInteger(values[2], "preparing_count"),
      totalRooms: nonNegativeInteger(values[3], "total_rooms"),
      availableRooms: [...availableRooms].sort((a, b) => Number(a) - Number(b)),
    };
  }).sort((a, b) => new Date(a.observedAt) - new Date(b.observedAt));
}

export function todaysHistory(history, now = new Date()) {
  const today = tokyoDateKey(now);
  return history.filter((entry) => tokyoDateKey(entry.observedAt) === today);
}

export function roomTimeline(history, roomNumber) {
  return history.map((entry) => ({
    observedAt: entry.observedAt,
    time: tokyoTimeLabel(entry.observedAt),
    available: entry.availableRooms.includes(roomNumber),
  }));
}

export { JST_TIME_ZONE };
