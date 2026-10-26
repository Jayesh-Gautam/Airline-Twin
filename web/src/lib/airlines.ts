// One muted, distinct colour per (fictional) airline - used on the map, charts and badges.
// Deliberately avoids the semantic emerald/rose/amber used for profit, loss and delays.
export const AIRLINE_COLORS: Record<number, string> = {
  1: "#8b93e8", // Northwind Air - indigo
  2: "#4cc2b5", // Blue Harbor Airlines - teal
  3: "#cdb184", // Atlantic Crown - sand
  4: "#b794f4", // Rhine Sky - violet
  5: "#e8a07f", // Bosphorus Wings - clay
  6: "#e58bc0", // Pacific Lantern - orchid
}

export function airlineColor(id: number | null | undefined): string {
  return (id != null && AIRLINE_COLORS[id]) || "#a1a1aa"
}

export const SPEED_LABELS: Record<number, string> = { 60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h" }
