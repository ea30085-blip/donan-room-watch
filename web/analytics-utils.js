import { FACILITY_KEYS } from "./facility-meta.js";

const JST_TIME_ZONE = "Asia/Tokyo";
const HOUR_MS = 60 * 60 * 1000;
const JST_OFFSET_MS = 9 * HOUR_MS;

export const WEEKDAY_LABELS = Object.freeze(["月", "火", "水", "木", "金", "土", "日"]);
export const TIME_BANDS = Object.freeze(
  Array.from({ length: 12 }, (_, index) => ({
    startHour: index * 2,
    label: `${String(index * 2).padStart(2, "0")}-${String((index + 1) * 2).padStart(2, "0")}`,
  })),
);

function checkedDate(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) throw new Error(`不正な日時です: ${value}`);
  return date;
}

function positiveInteger(value, label) {
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${label}は正の整数である必要があります`);
  }
  return value;
}

function average(values) {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function jstDateHourParts(value) {
  const date = checkedDate(value);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: JST_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const fields = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const dateKey = `${fields.year}-${fields.month}-${fields.day}`;
  const hour = Number(fields.hour);
  // dateKey is already the JST calendar date. Parsing that label at UTC midnight
  // preserves its calendar weekday; parsing it at +09:00 would shift to the
  // previous UTC date and mislabel every heatmap column.
  const utcDay = new Date(`${dateKey}T00:00:00Z`).getUTCDay();
  return {
    dateKey,
    hour,
    weekdayIndex: (utcDay + 6) % 7,
    key: `${dateKey}T${String(hour).padStart(2, "0")}`,
  };
}

export function completedWindowBounds(now = new Date(), hours = 168) {
  positiveInteger(hours, "hours");
  const nowMs = checkedDate(now).getTime();
  const endMs = Math.floor((nowMs + JST_OFFSET_MS) / HOUR_MS) * HOUR_MS - JST_OFFSET_MS;
  return {
    start: new Date(endMs - hours * HOUR_MS),
    end: new Date(endMs),
    expectedHours: hours,
  };
}

export function filterHistoryByRollingHours(
  history,
  hours,
  now = new Date(),
  { completedHoursOnly = false } = {},
) {
  positiveInteger(hours, "hours");
  const nowMs = checkedDate(now).getTime();
  const bounds = completedHoursOnly
    ? completedWindowBounds(now, hours)
    : { start: new Date(nowMs - hours * HOUR_MS), end: new Date(nowMs) };
  const startMs = bounds.start.getTime();
  const endMs = bounds.end.getTime();
  return history.filter((entry) => {
    const timestamp = checkedDate(entry.observedAt).getTime();
    return timestamp >= startMs && (completedHoursOnly ? timestamp < endMs : timestamp <= endMs);
  });
}

export function buildHourlyBuckets(history) {
  const bucketMap = new Map();
  for (const entry of history) {
    const parts = jstDateHourParts(entry.observedAt);
    const bucket = bucketMap.get(parts.key) || {
      ...parts,
      observations: [],
      availableCountTotal: 0,
      roomHits: Object.create(null),
    };
    bucket.observations.push(entry);
    bucket.availableCountTotal += entry.availableCount;
    for (const room of entry.availableRooms) {
      bucket.roomHits[room] = (bucket.roomHits[room] || 0) + 1;
    }
    bucketMap.set(parts.key, bucket);
  }

  return [...bucketMap.values()]
    .sort((a, b) => a.key.localeCompare(b.key))
    .map((bucket) => ({
      key: bucket.key,
      dateKey: bucket.dateKey,
      hour: bucket.hour,
      weekdayIndex: bucket.weekdayIndex,
      observationCount: bucket.observations.length,
      averageAvailableCount: bucket.availableCountTotal / bucket.observations.length,
      roomHits: { ...bucket.roomHits },
      observations: bucket.observations,
    }));
}

export function aggregateAverageAvailability(buckets) {
  return average(buckets.map((bucket) => bucket.averageAvailableCount));
}

export function calculateCoverage(buckets, expectedHours) {
  positiveInteger(expectedHours, "expectedHours");
  const observedHours = new Set(buckets.map((bucket) => bucket.key)).size;
  return {
    observedHours,
    expectedHours,
    percentage: Math.min(100, (observedHours / expectedHours) * 100),
  };
}

export function buildWeekdayTimeHeatmap(buckets) {
  const groups = Array.from({ length: 12 }, () =>
    Array.from({ length: 7 }, () => []),
  );
  for (const bucket of buckets) {
    groups[Math.floor(bucket.hour / 2)][bucket.weekdayIndex].push(
      bucket.averageAvailableCount,
    );
  }
  return TIME_BANDS.flatMap((band, bandIndex) =>
    WEEKDAY_LABELS.map((weekday, weekdayIndex) => {
      const values = groups[bandIndex][weekdayIndex];
      return {
        timeBand: band.label,
        startHour: band.startHour,
        weekday,
        weekdayIndex,
        averageAvailableCount: average(values),
        bucketCount: values.length,
      };
    }),
  );
}

export function facilityAvailabilityRates(buckets, masterRooms) {
  return FACILITY_KEYS.map((facility) => {
    const targetRooms = masterRooms
      .filter((room) => room.facilities.includes(facility))
      .map((room) => room.room);
    const targetSet = new Set(targetRooms);
    const bucketRates = buckets.map((bucket) => {
      const hits = bucket.observations.reduce(
        (count, observation) => count + Number(
          observation.availableRooms.some((room) => targetSet.has(room)),
        ),
        0,
      );
      return hits / bucket.observationCount;
    });
    return {
      facility,
      rate: average(bucketRates),
      targetRooms,
      bucketCount: bucketRates.length,
    };
  });
}

export function roomAvailabilityRates(buckets, masterRooms) {
  return masterRooms.map((room) => {
    const bucketRates = buckets.map(
      (bucket) => (bucket.roomHits[room.room] || 0) / bucket.observationCount,
    );
    return {
      room: room.room,
      type: room.type,
      facilities: [...room.facilities],
      rate: average(bucketRates),
      bucketCount: bucketRates.length,
    };
  }).sort((a, b) => {
    if (a.rate === null && b.rate === null) return Number(a.room) - Number(b.room);
    if (a.rate === null) return 1;
    if (b.rate === null) return -1;
    return b.rate - a.rate || Number(a.room) - Number(b.room);
  });
}

export function analyzeAvailability(history, masterRooms, hours, now = new Date()) {
  const filteredHistory = filterHistoryByRollingHours(history, hours, now, {
    completedHoursOnly: true,
  });
  const buckets = buildHourlyBuckets(filteredHistory);
  const bounds = completedWindowBounds(now, hours);
  return {
    hours,
    bounds,
    observationCount: filteredHistory.length,
    bucketCount: buckets.length,
    dayCount: new Set(buckets.map((bucket) => bucket.dateKey)).size,
    coverage: calculateCoverage(buckets, hours),
    averageAvailableCount: aggregateAverageAvailability(buckets),
    heatmap: buildWeekdayTimeHeatmap(buckets),
    facilityRates: facilityAvailabilityRates(buckets, masterRooms),
    roomRates: roomAvailabilityRates(buckets, masterRooms),
    buckets,
  };
}

export { HOUR_MS, JST_TIME_ZONE };
