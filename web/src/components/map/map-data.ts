import type { Flight } from "@/lib/api"

export type MapAirport = { iata: string; name: string; lat: number; lon: number; city: string; country: string; airlines: number[] }
export type MapRoute = { airline_id: number; route: string; origin: string; destination: string; arc: [number, number][] }
export type MapData = { airports: MapAirport[]; routes: MapRoute[] }

export const PLANE_PATH =
  "M12 2c.6 0 1 .7 1 1.6V9l7.5 4.3c.3.2.5.5.5.9v1.1c0 .3-.3.5-.6.4L13 13.5v4.8l2.2 1.6c.2.1.3.3.3.5v.8c0 .3-.3.5-.6.4L12 20.7l-2.9.9c-.3.1-.6-.1-.6-.4v-.8c0-.2.1-.4.3-.5l2.2-1.6v-4.8l-7.4 2.2c-.3.1-.6-.1-.6-.4v-1.1c0-.4.2-.7.5-.9L11 9V3.6C11 2.7 11.4 2 12 2z"

// SVG attributes can't resolve CSS variables, so the map uses resolved colours per theme.
export const MAP_COLORS = {
  dark: { onTime: "#34d399", delayed: "#fbbf24", departing: "#38bdf8", dot: "#e4e4e7", ring: "#52525b", land: "#27272a", border: "#3f3f46", label: "#a1a1aa" },
  light: { onTime: "#059669", delayed: "#d97706", departing: "#0284c7", dot: "#27272a", ring: "#a1a1aa", land: "#e4e4e7", border: "#d4d4d8", label: "#52525b" },
}

export function planeColor(f: Flight, dark: boolean): string {
  const c = dark ? MAP_COLORS.dark : MAP_COLORS.light
  if (f.delay_minutes >= 15) return c.delayed
  if (f.status === "Departed") return c.departing
  return c.onTime
}

/** Server longitudes are in [-180, 180]; route arcs are unwrapped. Put the plane on the same copy as its arc. */
export function alignLon(f: Flight, routes: Map<string, MapRoute>): number {
  const p = f.position!
  const r = routes.get(`${f.airline_id}:${f.route}`) ?? routes.get(`${f.airline_id}:${f.destination}-${f.origin}`)
  if (!r) return p.lon
  const forward = r.origin === f.origin
  const i = Math.round((forward ? p.progress : 1 - p.progress) * (r.arc.length - 1))
  const ref = r.arc[Math.max(0, Math.min(r.arc.length - 1, i))][1]
  let lon = p.lon
  while (lon - ref > 180) lon -= 360
  while (lon - ref < -180) lon += 360
  return lon
}
