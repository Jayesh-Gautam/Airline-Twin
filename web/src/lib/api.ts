export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"

export class ApiError extends Error {
  hint?: string
  constructor(message: string, hint?: string) {
    super(message)
    this.hint = hint
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API + path, { cache: "no-store", ...init })
  } catch {
    throw new ApiError("Backend not reachable", "Start it with: start.ps1 (or uvicorn backend.main:app --port 8000)")
  }
  if (!res.ok) {
    let body: { error?: string; hint?: string; detail?: unknown } = {}
    try {
      body = await res.json()
    } catch {}
    const detail = typeof body.detail === "string" ? body.detail : undefined
    throw new ApiError(body.error ?? detail ?? `HTTP ${res.status}`, body.hint)
  }
  return res.json() as Promise<T>
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return api<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  })
}

export function qs(params: Record<string, string | number | null | undefined>): string {
  const p = Object.entries(params).filter(([, v]) => v != null && v !== "")
  return p.length ? "?" + p.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&") : ""
}

// ---------------------------------------------------------------- types
export type Airline = { id: number; name: string; code: string; hub: string; fleet: number; routes: number }

export type Scenario = {
  demand: number
  delay_multiplier: number
  fuel_price: number
  bad_weather: { enabled: boolean; airports: string[] }
  grounded_aircraft: number[]
  real_life: boolean
}

export type Condition = { kind: "weather" | "atc" | "demand" | "aog"; label: string; start: string; end: string }

export type Conditions = {
  enabled: boolean
  fuel_price: number
  demand: number
  delay_index: number
  active: Condition[]
  upcoming: Condition[]
}

export type SimState = {
  clock: string
  day: string
  day_index: number
  weekday: string
  running: boolean
  speed: number
  speeds: number[]
  seed: number
  start_date: string
  scenario: Scenario
  event_seq: number
  error: string | null
  conditions: Conditions
}

export type FlightStatus = "Scheduled" | "Boarding" | "Delayed" | "Departed" | "In Flight" | "Landed" | "Cancelled"

export type Flight = {
  id: string
  day: string
  flight_number: string
  airline_id: number
  airline: string
  airline_code: string
  route: string
  origin: string
  destination: string
  distance_km: number
  block_h: number
  registration: string
  model: string
  capacity: number
  is_ferry: boolean
  status: FlightStatus
  std: string
  sta: string
  etd: string
  eta: string
  atd: string | null
  ata: string | null
  delay_minutes: number
  delay_reason: string | null
  cancel_reason: string | null
  pax: number
  load_factor: number
  break_even_lf: number | null
  revenue: number
  cost_so_far: number
  profit_so_far: number
  profit_projected: number
  revenue_lost: number
  fuel_kg_est: number
  loss: boolean
  position: { lat: number; lon: number; heading: number; progress: number } | null
}

export type SimEvent = {
  seq: number
  time: string
  day: string
  day_index: number
  kind: "status" | "delay" | "cancel" | "maintenance" | "loss" | "scenario" | "swap" | "reposition" | "disruption"
  text: string
  amount: number | null
  airline_id: number | null
  airline: string | null
  flight_id: string | null
  flight_number: string | null
  status: string | null
}

export type CostBreakdown = {
  fuel: number
  crew: number
  airport: number
  overhead: number
  delay: number
  compensation: number
  maintenance: number
  reposition: number
}

export type HourPoint = { h: number; revenue: number; cost: number; profit: number; pax: number }

export type LivePnl = {
  day: string
  day_index: number
  clock: string
  revenue: number
  pax: number
  seats: number
  flights: number
  departed: number
  landed: number
  cancelled: number
  delayed: number
  in_air: number
  revenue_lost: number
  cost: CostBreakdown
  cost_total: number
  profit: number
  load_factor: number | null
  hourly: HourPoint[]
  hourly_yesterday: HourPoint[]
  yesterday_same_time: HourPoint | null
  yesterday: { revenue: number; cost_total: number; profit: number; pax: number; flights: number } | null
}

export type DailyRow = {
  day: string
  day_index: number
  weekday: string
  closed: boolean
  revenue: number
  cost_total: number
  profit: number
  pax: number
  flights: number
  cancelled: number
  delayed: number
  load_factor: number | null
  revenue_lost: number
  cost: CostBreakdown
}

export type CauseFlight = {
  id: string
  flight_number: string
  route: string
  impact: number
  detail: string
  load_factor?: number
  break_even_lf?: number | null
  delay_minutes?: number
}

export type Cause = {
  key: string
  label: string
  impact: number
  count: number
  flights: CauseFlight[]
  cost?: number
  revenue_lost?: number
}

export type DayDetail = {
  totals: LivePnl & { cost: CostBreakdown }
  why: {
    day: string
    profit: number
    is_loss: boolean
    profitable_contribution: number
    causes: Cause[]
    reconciliation_gap: number
    note: string
  }
  flights: Flight[]
}

export type Period = "day" | "month" | "6m" | "year" | "ytd"

export type PeriodTotals = {
  revenue: number
  cost_total: number
  profit: number
  pax: number
  seats: number
  flights: number
  delayed: number
  cancelled: number
  revenue_lost: number
  load_factor: number | null
  cost: CostBreakdown
}

export type PeriodPnl = {
  period: Period
  start: string
  end: string
  window_days: number
  simulated_days: number
  first_simulated: string
  totals: PeriodTotals | null
  previous: PeriodTotals | null
  daily: (DailyRow & { seats: number; cumulative_profit: number })[]
}

export type StreamMsg = { state: SimState; flights: Flight[]; pnl: LivePnl; events: SimEvent[] }
