/**
 * Format an ISO datetime string (as returned by the backend's
 * `.isoformat()`) into "yyyy/MM/dd HH:mm" for display.
 * Falls back to the raw value if parsing fails, and "-" for null/empty.
 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const pad = (n: number) => String(n).padStart(2, "0");

  return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(
    date.getDate()
  )} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
