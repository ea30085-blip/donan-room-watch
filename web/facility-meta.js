export const FACILITY_META = Object.freeze({
  sauna: Object.freeze({ label: "サウナ", icon: "♨️" }),
  karaoke: Object.freeze({ label: "カラオケ", icon: "🎤" }),
  bath_tv: Object.freeze({ label: "浴室TV", icon: "📺" }),
  massage_chair: Object.freeze({ label: "マッサージ", icon: "💺" }),
  collagen_machine: Object.freeze({ label: "コラーゲン", icon: "✨" }),
  rainbow_blower_bath: Object.freeze({ label: "虹色ブロアー", icon: "🌈" }),
  blower_bath: Object.freeze({ label: "ブロアーバス", icon: "🛁" }),
});

export const FACILITY_KEYS = Object.freeze(Object.keys(FACILITY_META));

export function facilityText(key) {
  const meta = FACILITY_META[key];
  if (!meta) throw new Error(`未知の設備キーです: ${key}`);
  return `${meta.icon} ${meta.label}`;
}
