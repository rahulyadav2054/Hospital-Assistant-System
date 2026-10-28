/** "2026-11-02T09:00" -> "Mon 02 Nov · 09:00" (backend datetimes are hospital local time). */
export function formatWhen(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short" });
  const time = iso.slice(11, 16);
  return `${day.replace(",", "")} · ${time}`;
}

export function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatINR(n) {
  return n == null ? "" : `INR ${Number(n).toLocaleString("en-IN")}`;
}
