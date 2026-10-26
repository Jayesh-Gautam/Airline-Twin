"use client"

import * as React from "react"
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, XAxis, YAxis } from "recharts"
import { CalendarX2Icon, ChevronRightIcon, TrendingUpIcon } from "lucide-react"

import { EmptyState, Est, Label12, PageHeader, Signed } from "@/components/bits"
import { FlightSheet } from "@/components/flight-sheet"
import { KpiCard } from "@/components/kpi-card"
import { useSim } from "@/components/sim-provider"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, qs, type Cause, type DailyRow, type DayDetail, type Flight } from "@/lib/api"
import { dayLabel, money, pct } from "@/lib/format"
import { cn } from "@/lib/utils"

type RouteRow = {
  airline: string
  route: string
  flights: number
  cancelled: number
  load_factor: number | null
  break_even_lf: number | null
  revenue: number
  profit: number
  margin: number | null
}

const COST_CATS: { key: keyof DayDetail["totals"]["cost"]; label: string; color: string }[] = [
  { key: "fuel", label: "Fuel", color: "var(--chart-1)" },
  { key: "overhead", label: "Ownership & overhead", color: "var(--chart-2)" },
  { key: "crew", label: "Crew", color: "var(--chart-4)" },
  { key: "airport", label: "Airport fees", color: "var(--chart-3)" },
  { key: "delay", label: "Delay costs", color: "var(--delayed)" },
  { key: "compensation", label: "Compensation", color: "var(--loss)" },
  { key: "maintenance", label: "Maintenance", color: "oklch(0.55 0.08 300)" },
  { key: "reposition", label: "Repositioning", color: "oklch(0.6 0.05 250)" },
]

const barConfig = { profit: { label: "Profit", color: "var(--profit)" } } satisfies ChartConfig

function useDaily(airlineId: number | null, tick: unknown) {
  const [rows, setRows] = React.useState<DailyRow[] | null>(null)
  React.useEffect(() => {
    api<DailyRow[]>(`/sim/pnl/daily${qs({ airline: airlineId })}`).then(setRows).catch(() => setRows([]))
  }, [airlineId, tick])
  return rows
}

export default function DailyPnlPage() {
  const { airlineId, state, flights: liveFlights } = useSim()
  // refresh when the simulated hour changes (at most once per sim hour)
  const tick = state ? `${state.day}|${state.clock.slice(11, 13)}` : null
  const daily = useDaily(airlineId, tick)
  const [day, setDay] = React.useState<string | null>(null)
  const [detail, setDetail] = React.useState<DayDetail | null>(null)
  const [routes, setRoutes] = React.useState<RouteRow[] | null>(null)
  const [flight, setFlight] = React.useState<Flight | null>(null)

  // ?day=YYYY-MM-DD (from Live Operations' day table) wins; else the worst closed day, else the latest day
  const wanted = React.useRef<string | null>(null)
  React.useEffect(() => {
    wanted.current = new URLSearchParams(window.location.search).get("day")
  }, [])
  React.useEffect(() => {
    if (!daily?.length) return
    if (wanted.current && daily.some((d) => d.day === wanted.current)) {
      setDay(wanted.current)
      wanted.current = null
      return
    }
    if (day && daily.some((d) => d.day === day)) return
    const closed = daily.filter((d) => d.closed)
    const worst = [...closed].sort((a, b) => a.profit - b.profit)[0]
    setDay((worst && worst.profit < 0 ? worst : daily[daily.length - 1]).day)
  }, [daily, day])
  const prevAirline = React.useRef(airlineId)
  React.useEffect(() => {
    if (prevAirline.current !== airlineId) setDay(null)
    prevAirline.current = airlineId
  }, [airlineId])

  React.useEffect(() => {
    if (!day) return
    api<DayDetail>(`/sim/pnl/day/${day}${qs({ airline: airlineId })}`).then(setDetail).catch(() => setDetail(null))
  }, [day, airlineId, tick])
  React.useEffect(() => {
    api<RouteRow[]>(`/sim/routes${qs({ airline: airlineId })}`).then(setRoutes).catch(() => setRoutes([]))
  }, [airlineId, state?.day])

  const closed = daily?.filter((d) => d.closed) ?? []
  const lossDays = closed.filter((d) => d.profit < 0)
  const total = closed.reduce((s, d) => s + d.profit, 0)
  const worst = [...closed].sort((a, b) => a.profit - b.profit)[0]

  if (daily && daily.length === 0) {
    return (
      <div className="grid gap-4">
        <PageHeader title="Daily P&L" description="Which days lost money, and why" />
        <Card className="rounded-xl shadow-none">
          <EmptyState icon={CalendarX2Icon} title="No simulated days yet. Start the simulation to build the daily P&L." />
        </Card>
      </div>
    )
  }

  return (
    <div className="grid gap-4">
      <PageHeader title="Daily P&L" description="Which days lost money, and why. Revenue uses historical fares; every cost is an estimate." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard label="Days completed" value={daily ? closed.length : null} format={(v) => String(Math.round(v))} footer={daily ? `${daily.length - closed.length} in progress` : ""} />
        <KpiCard label="Loss-making days" value={daily ? lossDays.length : null} format={(v) => String(Math.round(v))} footer={closed.length ? `${pct(lossDays.length / closed.length, 0)} of completed days` : "–"} />
        <KpiCard label="Profit, completed days" estimate tone="auto" value={daily ? total : null} format={(v) => money(v, { sign: true })} />
        <KpiCard label="Worst day" estimate tone="auto" value={worst ? worst.profit : daily ? 0 : null} format={(v) => money(v, { sign: true })} footer={worst ? `Day ${worst.day_index} · ${dayLabel(worst.day)}` : "–"} />
      </div>

      <Card className="gap-2 rounded-xl shadow-none">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">Profit per simulated day <Est /></CardTitle>
          <span className="text-xs text-muted-foreground">click a bar to explain that day</span>
        </CardHeader>
        <CardContent>
          {daily ? (
            <ChartContainer config={barConfig} className="aspect-auto h-[240px] w-full">
              <BarChart data={daily} margin={{ left: 4, right: 8, top: 8 }} onClick={(e) => { const d = daily[Number(e?.activeTooltipIndex ?? -1)]; if (d) setDay(d.day) }}>
                <CartesianGrid vertical={false} strokeOpacity={0.4} />
                <XAxis dataKey="day_index" tickLine={false} axisLine={false} tickFormatter={(v) => `D${v}`} className="num" />
                <YAxis tickFormatter={(v) => money(v)} tickLine={false} axisLine={false} width={64} />
                <ReferenceLine y={0} stroke="var(--muted-foreground)" strokeOpacity={0.6} />
                <ChartTooltip
                  cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                  content={
                    <ChartTooltipContent
                      hideIndicator
                      labelFormatter={(_, p) => { const r = p?.[0]?.payload as DailyRow | undefined; return r ? `Day ${r.day_index} · ${dayLabel(r.day)}${r.closed ? "" : " (in progress)"}` : "" }}
                      formatter={(v, _n, item) => {
                        const r = item.payload as DailyRow
                        return (
                          <div className="grid w-full gap-1">
                            <div className="flex justify-between gap-6"><span className="text-muted-foreground">Profit</span><span className="num">{money(Number(v), { sign: true })}</span></div>
                            <div className="flex justify-between gap-6"><span className="text-muted-foreground">Revenue</span><span className="num">{money(r.revenue)}</span></div>
                            <div className="flex justify-between gap-6"><span className="text-muted-foreground">Flights · cancelled</span><span className="num">{r.flights} · {r.cancelled}</span></div>
                          </div>
                        )
                      }}
                    />
                  }
                />
                <Bar dataKey="profit" radius={[4, 4, 4, 4]} maxBarSize={36} className="cursor-pointer">
                  {daily.map((d) => (
                    <Cell key={d.day} fill={d.profit < 0 ? "var(--loss)" : "var(--profit)"} fillOpacity={d.day === day ? 1 : d.closed ? 0.45 : 0.25} />
                  ))}
                </Bar>
              </BarChart>
            </ChartContainer>
          ) : (
            <Skeleton className="h-[240px] w-full" />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-12">
        <WhyCard detail={detail} className="xl:col-span-7" onFlight={(id) => setFlight(detail?.flights.find((f) => f.id === id) ?? liveFlights.find((f) => f.id === id) ?? null)} />
        <BreakdownCard detail={detail} className="xl:col-span-5" onFlight={setFlight} />
      </div>

      <Card className="gap-3 rounded-xl shadow-none">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">Break-even load factor by route <Est /></CardTitle>
          <CardDescription>Break-even = planned cost ÷ revenue of a full flight. Routes flying below it lose money on every departure.</CardDescription>
        </CardHeader>
        <CardContent>
          <RouteTable rows={routes} />
        </CardContent>
      </Card>
      <FlightSheet flight={flight} onClose={() => setFlight(null)} />
    </div>
  )
}

function WhyCard({ detail, className, onFlight }: { detail: DayDetail | null; className?: string; onFlight: (id: string) => void }) {
  if (!detail) return <Skeleton className={cn("h-[420px] rounded-xl", className)} />
  const w = detail.why
  const t = detail.totals
  const max = Math.max(w.profitable_contribution, ...w.causes.map((c) => Math.abs(c.impact)), 1)
  return (
    <Card className={cn("gap-4 rounded-xl shadow-none", className)}>
      <CardHeader>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <CardTitle className="text-base font-semibold">
            {w.is_loss ? "Why this day lost money" : "What drove this day's result"}
          </CardTitle>
          <span className="text-sm text-muted-foreground">
            {dayLabel(w.day)}
          </span>
        </div>
        <div className="flex items-baseline gap-3">
          <Signed value={w.profit} format={(v) => money(v, { sign: true })} className="text-[32px] leading-10 font-semibold" />
          <Est />
          <span className="text-sm text-muted-foreground">
            {money(t.revenue)} revenue · {money(t.cost_total)} cost
          </span>
        </div>
      </CardHeader>
      <CardContent className="grid gap-1">
        <CauseRow
          label="Profitable flights"
          detail="revenue above their normal operating cost"
          impact={w.profitable_contribution}
          max={max}
          positive
        />
        {w.causes.map((c) => (
          <CauseItem key={c.key} cause={c} max={max} onFlight={onFlight} />
        ))}
        {w.causes.length === 0 ? <p className="py-3 text-sm text-muted-foreground">No losses, delays or cancellations on this day.</p> : null}
        <p className="mt-3 text-xs text-muted-foreground">
          The rows add up to the day&apos;s result. {w.causes.some((c) => c.revenue_lost) ? "Cancellation rows also count the revenue that was never earned. " : ""}
          Amounts are illustrative estimates (config.py).
        </p>
      </CardContent>
    </Card>
  )
}

function Bar1({ value, max, positive }: { value: number; max: number; positive?: boolean }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
      <div className={cn("h-full rounded-full", positive ? "bg-profit" : "bg-loss")} style={{ width: `${Math.max(2, (Math.abs(value) / max) * 100)}%` }} />
    </div>
  )
}

function CauseRow({ label, detail, impact, max, positive, chevron }: { label: string; detail?: string; impact: number; max: number; positive?: boolean; chevron?: boolean }) {
  return (
    <div className="grid w-full grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1.5 rounded-lg px-2 py-2 text-left">
      <span className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
        {chevron ? <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" strokeWidth={1.5} /> : positive ? <TrendingUpIcon className="size-4 shrink-0 text-profit" strokeWidth={1.5} /> : null}
        <span className="truncate">{label}</span>
        {detail ? <span className="hidden truncate font-normal text-muted-foreground sm:inline">· {detail}</span> : null}
      </span>
      <span className={cn("num text-sm font-medium", positive ? "text-profit" : "text-loss")}>{money(impact, { sign: true })}</span>
      <div className="col-span-2">
        <Bar1 value={impact} max={max} positive={positive} />
      </div>
    </div>
  )
}

function CauseItem({ cause, max, onFlight }: { cause: Cause; max: number; onFlight: (id: string) => void }) {
  const extra = cause.revenue_lost ? `${money(cause.cost)} cost + ${money(cause.revenue_lost)} revenue lost` : undefined
  return (
    <Collapsible className="group rounded-lg hover:bg-muted/40">
      <CollapsibleTrigger className="w-full rounded-lg focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
        <CauseRow label={cause.label} detail={extra} impact={cause.impact} max={max} chevron />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mb-2 ml-7 grid gap-0.5 border-l pl-3">
          {cause.flights.slice(0, 12).map((f) => (
            <li key={f.id}>
              <button onClick={() => onFlight(f.id)} className="flex w-full items-center gap-3 rounded px-2 py-1 text-left text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
                <span className="num w-20 shrink-0">{f.flight_number}</span>
                <span className="num w-20 shrink-0 text-muted-foreground">{f.route}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">{f.detail}</span>
                <span className="num text-loss">{money(f.impact, { sign: true })}</span>
              </button>
            </li>
          ))}
          {cause.flights.length > 12 ? <li className="px-2 py-1 text-xs text-muted-foreground">+ {cause.flights.length - 12} more</li> : null}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  )
}

function BreakdownCard({ detail, className, onFlight }: { detail: DayDetail | null; className?: string; onFlight: (f: Flight) => void }) {
  if (!detail) return <Skeleton className={cn("h-[420px] rounded-xl", className)} />
  const t = detail.totals
  const row: Record<string, number | string> = { name: "Cost" }
  COST_CATS.forEach((c) => (row[c.key] = t.cost[c.key] ?? 0))
  const config = Object.fromEntries(COST_CATS.map((c) => [c.key, { label: c.label, color: c.color }])) as ChartConfig
  const data = [{ name: "Revenue", revenue: t.revenue }, row]
  const losers = detail.flights.filter((f) => !f.is_ferry && f.status !== "Cancelled" && f.status === "Landed" && f.profit_so_far < 0).slice(0, 8)
  return (
    <Card className={cn("gap-4 rounded-xl shadow-none", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium">Revenue vs cost by category <Est /></CardTitle>
      </CardHeader>
      <CardContent className="grid gap-5">
        <ChartContainer config={{ ...config, revenue: { label: "Revenue", color: "var(--muted-foreground)" } }} className="aspect-auto h-[120px] w-full">
          <BarChart data={data} layout="vertical" margin={{ left: 0, right: 8 }} barCategoryGap={10}>
            <XAxis type="number" hide />
            <YAxis type="category" dataKey="name" tickLine={false} axisLine={false} width={64} />
            <ChartTooltip cursor={false} content={<ChartTooltipContent formatter={(v, n) => (
              <div className="flex w-full justify-between gap-6"><span className="text-muted-foreground">{(config[String(n)]?.label as string) ?? "Revenue"}</span><span className="num">{money(Number(v))}</span></div>
            )} />} />
            <Bar dataKey="revenue" stackId="a" fill="var(--color-revenue)" radius={4} />
            {COST_CATS.map((c, i) => (
              <Bar key={c.key} dataKey={c.key} stackId="a" fill={`var(--color-${c.key})`} radius={i === COST_CATS.length - 1 ? [0, 4, 4, 0] : 0} />
            ))}
          </BarChart>
        </ChartContainer>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
          {COST_CATS.filter((c) => (t.cost[c.key] ?? 0) > 0).map((c) => (
            <div key={c.key} className="flex items-center gap-2">
              <span className="size-2 rounded-sm" style={{ background: c.color }} />
              <span className="text-muted-foreground">{c.label}</span>
              <span className="num ml-auto">{money(t.cost[c.key])}</span>
            </div>
          ))}
        </div>
        <div>
          <Label12>Loss-making flights</Label12>
          {losers.length === 0 ? (
            <p className="mt-2 text-sm text-muted-foreground">None on this day.</p>
          ) : (
            <ul className="mt-1 divide-y">
              {losers.map((f) => (
                <li key={f.id}>
                  <button onClick={() => onFlight(f)} className="flex w-full items-center gap-3 py-2 text-left text-sm hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
                    <span className="num w-20">{f.flight_number}</span>
                    <span className="num w-20 text-muted-foreground">{f.origin}–{f.destination}</span>
                    <span className="num text-xs text-muted-foreground">LF {pct(f.load_factor, 0)}{f.delay_minutes >= 15 ? ` · late ${f.delay_minutes}m` : ""}</span>
                    <span className="num ml-auto text-loss">{money(f.profit_so_far, { sign: true })}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function RouteTable({ rows }: { rows: RouteRow[] | null }) {
  if (!rows) return <Skeleton className="h-64 w-full" />
  if (!rows.length) return <p className="text-sm text-muted-foreground">No flights have operated yet.</p>
  return (
    <div className="max-h-[420px] overflow-auto rounded-lg border">
      <Table className="text-[13px]">
        <TableHeader className="sticky top-0 z-10 bg-background/95 backdrop-blur">
          <TableRow className="hover:bg-transparent">
            <TableHead>Route</TableHead>
            <TableHead className="hidden md:table-cell">Airline</TableHead>
            <TableHead className="text-right">Flights</TableHead>
            <TableHead className="text-right">Load factor</TableHead>
            <TableHead className="text-right">Break-even</TableHead>
            <TableHead className="text-right">Revenue</TableHead>
            <TableHead className="text-right">Profit</TableHead>
            <TableHead className="text-right">Margin</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const below = r.load_factor != null && r.break_even_lf != null && r.load_factor < r.break_even_lf
            return (
              <TableRow key={`${r.airline}${r.route}`} className={cn("h-10 border-l-2 border-l-transparent", r.profit < 0 && "border-l-loss")}>
                <TableCell className="num font-medium">{r.route}</TableCell>
                <TableCell className="hidden text-muted-foreground md:table-cell">{r.airline}</TableCell>
                <TableCell className="num text-right">{r.flights}{r.cancelled ? <span className="text-loss"> +{r.cancelled}✕</span> : null}</TableCell>
                <TableCell className={cn("num text-right", below && "text-loss")}>{pct(r.load_factor)}</TableCell>
                <TableCell className="num text-right text-muted-foreground">{pct(r.break_even_lf)}</TableCell>
                <TableCell className="num text-right">{money(r.revenue)}</TableCell>
                <TableCell className="text-right"><Signed value={r.profit} format={(v) => money(v, { sign: true })} /></TableCell>
                <TableCell className="num text-right">
                  {r.margin != null ? <Badge variant="outline" className={cn("num font-normal", r.margin < 0 ? "text-loss" : "text-profit")}>{pct(r.margin)}</Badge> : "–"}
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
