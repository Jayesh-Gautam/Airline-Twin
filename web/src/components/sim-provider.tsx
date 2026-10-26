"use client"

import * as React from "react"
import { toast } from "sonner"

import {
  API,
  ApiError,
  api,
  post,
  type Airline,
  type Flight,
  type LivePnl,
  type Scenario,
  type SimEvent,
  type SimState,
  type StreamMsg,
} from "@/lib/api"
import { money } from "@/lib/format"

type SimContext = {
  airlines: Airline[]
  airlineId: number | null
  setAirlineId: (id: number | null) => void
  airline: Airline | null
  connected: boolean
  error: ApiError | null
  state: SimState | null
  flights: Flight[]
  pnl: LivePnl | null
  events: SimEvent[]
  busy: boolean
  start: () => Promise<void>
  pause: () => Promise<void>
  reset: () => Promise<void>
  nextDay: () => Promise<void>
  advance: (days: number) => Promise<void>
  setSpeed: (speed: number) => Promise<void>
  applyScenario: (s: Partial<Scenario>) => Promise<void>
}

const Ctx = React.createContext<SimContext | null>(null)
const STORAGE_KEY = "airline-twin:airline"
const DEFAULT_AIRLINE = 6

export function useSim() {
  const c = React.useContext(Ctx)
  if (!c) throw new Error("useSim must be used inside <SimProvider>")
  return c
}

export function SimProvider({ children }: { children: React.ReactNode }) {
  const [airlines, setAirlines] = React.useState<Airline[]>([])
  const [airlineId, setAirlineIdState] = React.useState<number | null>(null)
  const [ready, setReady] = React.useState(false)
  const [connected, setConnected] = React.useState(false)
  const [error, setError] = React.useState<ApiError | null>(null)
  const [msg, setMsg] = React.useState<Omit<StreamMsg, "events"> | null>(null)
  const [events, setEvents] = React.useState<SimEvent[]>([])
  const [busy, setBusy] = React.useState(false)
  const toastQueue = React.useRef<SimEvent[]>([])

  // airlines + remembered selection
  React.useEffect(() => {
    let alive = true
    const load = () =>
      api<Airline[]>("/airlines")
        .then((a) => {
          if (!alive) return
          setAirlines(a)
          setError(null)
          let saved: string | null = null
          try {
            saved = localStorage.getItem(STORAGE_KEY)
          } catch {}
          const id = saved === "all" ? null : saved ? Number(saved) : DEFAULT_AIRLINE
          setAirlineIdState(saved === "all" || a.some((x) => x.id === id) ? id : (a[0]?.id ?? null))
          setReady(true)
        })
        .catch((e: ApiError) => {
          if (!alive) return
          setError(e)
          setTimeout(load, 3000)
        })
    load()
    return () => {
      alive = false
    }
  }, [])

  const setAirlineId = React.useCallback((id: number | null) => {
    setAirlineIdState(id)
    try {
      localStorage.setItem(STORAGE_KEY, id == null ? "all" : String(id))
    } catch {}
  }, [])

  // live stream (SSE), re-opened when the airline changes
  React.useEffect(() => {
    if (!ready) return
    setEvents([])
    setMsg(null)
    const url = `${API}/sim/stream${airlineId != null ? `?airline=${airlineId}` : ""}`
    const es = new EventSource(url)
    let first = true
    es.onopen = () => {
      setConnected(true)
      setError(null)
    }
    es.onerror = () => setConnected(false)
    es.onmessage = (ev) => {
      const m = JSON.parse(ev.data) as StreamMsg
      setMsg({ state: m.state, flights: m.flights, pnl: m.pnl })
      if (m.events.length) {
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => e.seq))
          const fresh = m.events.filter((e) => !seen.has(e.seq))
          return [...fresh, ...prev].slice(0, 300)
        })
        if (!first) toastQueue.current.push(...m.events.filter((e) => e.kind === "loss" || e.kind === "cancel"))
      }
      first = false
    }
    return () => es.close()
  }, [ready, airlineId])

  // at most one toast every 1.5 s; bursts are summarised
  React.useEffect(() => {
    const t = setInterval(() => {
      const q = toastQueue.current
      if (!q.length) return
      toastQueue.current = []
      const cancels = q.filter((e) => e.kind === "cancel")
      const losses = q.filter((e) => e.kind === "loss")
      if (cancels.length === 1 && !losses.length) {
        toast.error(cancels[0].text, { description: `Impact ${money(cancels[0].amount)} · est.` })
      } else if (losses.length === 1 && !cancels.length) {
        toast.warning(losses[0].text, { description: `Projected result ${money(losses[0].amount)} · est.` })
      } else {
        const parts = []
        if (cancels.length) parts.push(`${cancels.length} cancelled`)
        if (losses.length) parts.push(`${losses.length} loss-making`)
        toast.warning(`${parts.join(", ")} flights`, { description: q[0].text })
      }
    }, 1500)
    return () => clearInterval(t)
  }, [])

  const run = React.useCallback(async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await fn()
    } catch (e) {
      const err = e as ApiError
      toast.error(err.message, { description: err.hint })
    } finally {
      setBusy(false)
    }
  }, [])

  const value: SimContext = {
    airlines,
    airlineId,
    setAirlineId,
    airline: airlines.find((a) => a.id === airlineId) ?? null,
    connected,
    error,
    state: msg?.state ?? null,
    flights: msg?.flights ?? [],
    pnl: msg?.pnl ?? null,
    events,
    busy,
    start: () => run(() => post("/sim/start")),
    pause: () => run(() => post("/sim/pause")),
    reset: () => run(() => post("/sim/reset")),
    nextDay: () => run(() => post("/sim/next-day")),
    advance: (days) =>
      run(async () => {
        const id = toast.loading(`Simulating ${days} days…`)
        try {
          await post("/sim/advance", { days })
          toast.success(`Fast-forwarded ${days} days`, { id })
        } catch (e) {
          toast.dismiss(id)
          throw e
        }
      }),
    setSpeed: (speed) => run(() => post("/sim/speed", { speed })),
    applyScenario: (s) =>
      run(async () => {
        await post("/sim/scenario", s)
        toast.success("Scenario applied", { description: "Changes take effect from the current sim time." })
      }),
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
