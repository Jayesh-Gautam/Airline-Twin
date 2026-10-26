"use client"

import * as React from "react"
import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts"
import { PlayIcon } from "lucide-react"

import { AnimatedNumber, EmptyState, Est, Label12, PageHeader } from "@/components/bits"
import { EventFeed } from "@/components/event-feed"
import { FlightSheet } from "@/components/flight-sheet"
import { FlightTable } from "@/components/flight-table"
import { KpiCard } from "@/components/kpi-card"
import { CoverageNote, DaysTable, PERIODS, PeriodChart, PeriodKpis, PeriodToggle, usePeriodPnl } from "@/components/period-view"
import { useSim } from "@/components/sim-provider"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import type { Flight, Period } from "@/lib/api"
import { dayLabel, int, money, pct } from "@/lib/format"

const rel = (a: number | undefined, b: number | undefined) =>
  a == null || b == null || Math.abs(b) < 1 ? null : (a - b) / Math.abs(b)

const chartConfig = {
  today: { label: "Today", color: "var(--primary)" },
  yesterday: { label: "Yesterday", color: "var(--muted-foreground)" },
} satisfies ChartConfig

export default function LiveOperations() {
  const { state, pnl, flights, airline, airlineId, start, advance, busy } = useSim()
  const [selected, setSelected] = React.useState<string | null>(null)
  const [period, setPeriodState] = React.useState<Period>("day")
  React.useEffect(() => {
    try {
      const p = localStorage.getItem("airline-twin:period") as Period | null
      if (p && PERIODS.some((x) => x.value === p)) setPeriodState(p)
    } catch {}
  }, [])
  const setPeriod = (p: Period) => {
    setPeriodState(p)
    try {
      localStorage.setItem("airline-twin:period", p)
    } catch {}
  }
  const tick = state ? `${state.day}|${state.clock.slice(11, 13)}` : null
  const periodData = usePeriodPnl(airlineId, period, tick)
  const periodInfo = PERIODS.find((p) => p.value === period)!
  const selectedFlight: Flight | null = flights.find((f) => f.id === selected) ?? null

  const ys = pnl?.yesterday_same_time ?? undefined
  const idle = state && !state.running && pnl && pnl.departed === 0
  const series = React.useMemo(() => {
    if (!pnl) return []
    const rows = new Map<number, { h: number; today?: number; yesterday?: number }>()
    rows.set(0, { h: 0, today: 0, yesterday: pnl.hourly_yesterday.length ? 0 : undefined })
    for (const p of pnl.hourly_yesterday) rows.set(p.h, { ...(rows.get(p.h) ?? { h: p.h }), yesterday: p.profit })
    for (const p of pnl.hourly) rows.set(p.h, { ...(rows.get(p.h) ?? { h: p.h }), today: p.profit })
    return [...rows.values()].sort((a, b) => a.h - b.h)
  }, [pnl])

  return (
    <div className="grid gap-4">
      <PageHeader
        title="Live Operations"
        description={
          <>
            {airline ? `${airline.name} (fictional) · hub ${airline.hub} · ${airline.fleet} aircraft` : "All six fictional airlines"}
            {period === "day"
              ? pnl ? <> · {dayLabel(pnl.day)}</> : null
              : periodData ? <> · {periodInfo.long}: {dayLabel(periodData.start)} – {dayLabel(periodData.end)}</> : null}
          </>
        }
      >
        <PeriodToggle value={period} onChange={setPeriod} />
      </PageHeader>

      {period !== "day" ? (
        <>
          {periodData ? <CoverageNote data={periodData} onAdvance={advance} busy={busy} /> : null}
          <PeriodKpis data={periodData} />
          <PeriodChart data={periodData} title={periodInfo.long.toLowerCase()} />
        </>
      ) : null}

      {period === "day" && idle ? (
        <Card className="rounded-xl shadow-none">
          <EmptyState icon={PlayIcon} title="No simulation running. Start it to watch the schedule fly, minute by minute." action="Start simulation" onAction={start} className="py-6" />
        </Card>
      ) : null}

      {period === "day" ? (
      <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-12">
        <KpiCard
          className="col-span-2 lg:col-span-4"
          hero
          label="Live profit today"
          estimate
          tone="auto"
          live={state?.running}
          value={pnl?.profit ?? null}
          format={(v) => money(v, { sign: true })}
          delta={rel(pnl?.profit, ys?.profit)}
          deltaLabel="vs same time yesterday"
          spark={pnl ? [0, ...pnl.hourly.map((h) => h.profit)] : undefined}
        />
        <KpiCard className="lg:col-span-2" label="Revenue" value={pnl?.revenue ?? null} format={money} delta={rel(pnl?.revenue, ys?.revenue)} deltaLabel="vs yesterday" footer="booked at departure" />
        <KpiCard className="lg:col-span-2" label="Cost" estimate value={pnl?.cost_total ?? null} format={money} footer="accrues in flight" />
        <KpiCard className="lg:col-span-2" label="Passengers" value={pnl?.pax ?? null} format={int} footer={pnl?.load_factor != null ? `load factor ${pct(pnl.load_factor)}` : "no departures yet"} />
        <Card className="col-span-2 flex flex-col justify-between gap-3 rounded-xl p-4 shadow-none lg:col-span-2">
          <Label12>Operations</Label12>
          {pnl ? (
            <div className="grid grid-cols-3 gap-2">
              {[
                { k: "In air", v: pnl.in_air, c: "" },
                { k: "Delayed", v: pnl.delayed, c: pnl.delayed ? "text-delayed" : "" },
                { k: "Cancelled", v: pnl.cancelled, c: pnl.cancelled ? "text-loss" : "" },
              ].map((x) => (
                <div key={x.k}>
                  <AnimatedNumber value={x.v} format={int} className={`block text-[28px] leading-8 font-semibold ${x.c}`} />
                  <span className="text-xs text-muted-foreground">{x.k}</span>
                </div>
              ))}
            </div>
          ) : (
            <Skeleton className="h-12 w-full" />
          )}
          <span className="h-4 text-xs text-muted-foreground">{pnl ? `${pnl.flights} flights today` : ""}</span>
        </Card>
      </div>

      <Card className="gap-2 rounded-xl shadow-none">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            Cumulative profit through the day <Est />
          </CardTitle>
          <span className="text-xs text-muted-foreground">revenue at departure, costs as flights progress</span>
        </CardHeader>
        <CardContent>
          {pnl ? (
            <ChartContainer config={chartConfig} className="aspect-auto h-[240px] w-full">
              <LineChart data={series} margin={{ left: 4, right: 12, top: 8 }}>
                <CartesianGrid vertical={false} strokeOpacity={0.4} />
                <XAxis dataKey="h" type="number" domain={[0, 24]} ticks={[0, 3, 6, 9, 12, 15, 18, 21, 24]} tickFormatter={(h) => `${String(h).padStart(2, "0")}:00`} tickLine={false} axisLine={false} className="num" />
                <YAxis tickFormatter={(v) => money(v)} tickLine={false} axisLine={false} width={64} />
                <ReferenceLine y={0} stroke="var(--border)" />
                <ChartTooltip
                  content={
                    <ChartTooltipContent
                      labelFormatter={(_, p) => {
                        const h = Number(p?.[0]?.payload?.h ?? 0)
                        return `${String(Math.floor(h)).padStart(2, "0")}:${String(Math.round((h % 1) * 60)).padStart(2, "0")}`
                      }}
                      formatter={(v, name) => (
                        <div className="flex w-full justify-between gap-4">
                          <span className="text-muted-foreground">{chartConfig[name as keyof typeof chartConfig]?.label ?? name}</span>
                          <span className="num">{money(Number(v), { sign: true })}</span>
                        </div>
                      )}
                    />
                  }
                />
                <Line dataKey="yesterday" stroke="var(--color-yesterday)" strokeDasharray="4 4" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls />
                <Line dataKey="today" stroke="var(--color-today)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />
              </LineChart>
            </ChartContainer>
          ) : (
            <Skeleton className="h-[240px] w-full" />
          )}
        </CardContent>
      </Card>
      </>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-12">
        <Card className="gap-3 rounded-xl shadow-none xl:col-span-8">
          <CardHeader>
            <CardTitle className="text-sm font-medium">
              {period === "day" ? "Today's flights" : `Days · ${periodInfo.long.toLowerCase()}`}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {period !== "day" ? (
              <DaysTable data={periodData} />
            ) : state ? (
              <FlightTable flights={flights} onSelect={(f) => setSelected(f.id)} />
            ) : (
              <Skeleton className="h-[520px] w-full" />
            )}
          </CardContent>
        </Card>
        <Card className="gap-3 rounded-xl shadow-none xl:col-span-4">
          <CardHeader>
            <CardTitle className="text-sm font-medium">{period === "day" ? "Event feed" : "Live event feed"}</CardTitle>
          </CardHeader>
          <CardContent className="h-full">
            <EventFeed />
          </CardContent>
        </Card>
      </div>
      <FlightSheet flight={selectedFlight} onClose={() => setSelected(null)} />
    </div>
  )
}
