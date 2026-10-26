"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ReferenceLine, XAxis, YAxis } from "recharts"
import { CalendarRangeIcon, FastForwardIcon } from "lucide-react"

import { AnimatedNumber, EmptyState, Est, Label12, Signed } from "@/components/bits"
import { KpiCard } from "@/components/kpi-card"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api, qs, type Period, type PeriodPnl } from "@/lib/api"
import { compact, dayLabel, int, money, pct } from "@/lib/format"
import { cn } from "@/lib/utils"

export const PERIODS: { value: Period; label: string; long: string }[] = [
  { value: "day", label: "Day", long: "Today" },
  { value: "month", label: "Month", long: "Last 30 days" },
  { value: "6m", label: "6M", long: "Last 6 months" },
  { value: "year", label: "Year", long: "Last 12 months" },
  { value: "ytd", label: "YTD", long: "Year to date" },
]

export function PeriodToggle({ value, onChange }: { value: Period; onChange: (p: Period) => void }) {
  return (
    <ToggleGroup type="single" size="sm" variant="outline" value={value} onValueChange={(v) => v && onChange(v as Period)} aria-label="Period">
      {PERIODS.map((p) => (
        <ToggleGroupItem key={p.value} value={p.value} className="px-3 text-xs" aria-label={p.long}>
          {p.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}

/** Period P&L, refreshed when the period/airline changes and once per simulated hour. */
export function usePeriodPnl(airlineId: number | null, period: Period, tick: string | null) {
  const [data, setData] = React.useState<PeriodPnl | null>(null)
  const key = `${airlineId}|${period}`
  const last = React.useRef(key)
  React.useEffect(() => {
    if (period === "day") return
    if (last.current !== key) {
      last.current = key
      setData(null)
    }
    let alive = true
    api<PeriodPnl>(`/sim/pnl/period${qs({ airline: airlineId, period })}`)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null))
    return () => {
      alive = false
    }
  }, [airlineId, period, tick, key])
  return data
}

const rel = (a?: number, b?: number) => (a == null || b == null || Math.abs(b) < 1 ? null : (a - b) / Math.abs(b))
const shortDay = (iso: string) => dayLabel(iso).slice(4)

export function PeriodKpis({ data }: { data: PeriodPnl | null }) {
  const t = data?.totals ?? null
  const p = data?.previous ?? undefined
  const label = "vs previous period"
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-12">
      <KpiCard
        className="col-span-2 lg:col-span-4"
        hero
        label="Profit"
        estimate
        tone="auto"
        value={data ? (t?.profit ?? 0) : null}
        format={(v) => money(v, { sign: true })}
        delta={rel(t?.profit, p?.profit)}
        deltaLabel={label}
        footer={data ? `${data.simulated_days} days simulated` : ""}
        spark={data?.daily.map((d) => d.cumulative_profit)}
      />
      <KpiCard className="lg:col-span-2" label="Revenue" value={data ? (t?.revenue ?? 0) : null} format={money} delta={rel(t?.revenue, p?.revenue)} deltaLabel="vs prev." footer="real fares" />
      <KpiCard className="lg:col-span-2" label="Cost" estimate value={data ? (t?.cost_total ?? 0) : null} format={money} delta={rel(t?.cost_total, p?.cost_total)} deltaLabel="vs prev." footer="all categories" />
      <KpiCard className="lg:col-span-2" label="Passengers" value={data ? (t?.pax ?? 0) : null} format={compact} footer={t?.load_factor != null ? `load factor ${pct(t.load_factor)}` : "no departures yet"} />
      <Card className="col-span-2 flex flex-col justify-between gap-3 rounded-xl p-4 shadow-none lg:col-span-2">
        <Label12>Flights</Label12>
        {data ? (
          <div className="min-w-0">
            <AnimatedNumber value={t?.flights ?? 0} format={compact} className="block truncate text-[28px] leading-8 font-semibold" />
            <div className="mt-1 flex gap-3 text-xs whitespace-nowrap">
              <span className={t?.delayed ? "text-delayed" : "text-muted-foreground"}>
                <span className="num">{compact(t?.delayed ?? 0)}</span> delayed
              </span>
              <span className={t?.cancelled ? "text-loss" : "text-muted-foreground"}>
                <span className="num">{compact(t?.cancelled ?? 0)}</span> cancelled
              </span>
            </div>
          </div>
        ) : (
          <Skeleton className="h-12 w-full" />
        )}
        <span className="h-4 truncate text-xs text-muted-foreground">
          {t ? `delay rate ${pct(t.flights ? t.delayed / t.flights : 0)}` : ""}
        </span>
      </Card>
    </div>
  )
}

export function CoverageNote({ data, onAdvance, busy }: { data: PeriodPnl; onAdvance: (days: number) => void; busy: boolean }) {
  if (data.simulated_days >= data.window_days) return null
  const missing = data.window_days - data.simulated_days
  const startedLater = data.first_simulated > data.start
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 text-sm">
      <CalendarRangeIcon className="size-4 text-muted-foreground" strokeWidth={1.5} />
      <span className="text-muted-foreground">
        <span className="num text-foreground">{data.simulated_days}</span> of <span className="num">{data.window_days}</span> days in this period have been simulated
        {startedLater ? ` (the simulation starts on ${dayLabel(data.first_simulated)})` : ""}.
      </span>
      <div className="ml-auto flex items-center gap-1.5">
        <span className="text-xs text-muted-foreground">Fast-forward</span>
        {[7, 30, 90].filter((d, i) => i === 0 || d <= Math.max(missing, 30)).map((d) => (
          <Button key={d} size="xs" variant="outline" disabled={busy} onClick={() => onAdvance(d)} className="num gap-1">
            <FastForwardIcon className="size-3" strokeWidth={1.5} />+{d}d
          </Button>
        ))}
      </div>
    </div>
  )
}

const chartConfig = {
  profit: { label: "Daily profit", color: "var(--profit)" },
  cumulative_profit: { label: "Cumulative profit", color: "var(--primary)" },
} satisfies ChartConfig

export function PeriodChart({ data, title }: { data: PeriodPnl | null; title: string }) {
  const [mode, setMode] = React.useState<"daily" | "cumulative">("daily")
  const rows = data?.daily ?? []
  const tooltip = (
    <ChartTooltip
      cursor={{ fill: "var(--muted)", opacity: 0.4 }}
      content={
        <ChartTooltipContent
          hideIndicator
          labelFormatter={(_, p) => {
            const r = p?.[0]?.payload as PeriodPnl["daily"][number] | undefined
            return r ? `Day ${r.day_index} · ${dayLabel(r.day)}${r.closed ? "" : " (in progress)"}` : ""
          }}
          formatter={(_v, _n, item) => {
            const r = item.payload as PeriodPnl["daily"][number]
            return (
              <div className="grid w-full gap-1">
                <div className="flex justify-between gap-6"><span className="text-muted-foreground">Profit</span><span className="num">{money(r.profit, { sign: true })}</span></div>
                <div className="flex justify-between gap-6"><span className="text-muted-foreground">Cumulative</span><span className="num">{money(r.cumulative_profit, { sign: true })}</span></div>
                <div className="flex justify-between gap-6"><span className="text-muted-foreground">Revenue</span><span className="num">{money(r.revenue)}</span></div>
                <div className="flex justify-between gap-6"><span className="text-muted-foreground">Delayed · cancelled</span><span className="num">{r.delayed} · {r.cancelled}</span></div>
              </div>
            )
          }}
        />
      }
    />
  )
  return (
    <Card className="gap-2 rounded-xl shadow-none">
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium">
          {mode === "daily" ? "Profit per day" : "Cumulative profit"} · {title} <Est />
        </CardTitle>
        <ToggleGroup type="single" size="sm" value={mode} onValueChange={(v) => v && setMode(v as "daily" | "cumulative")} aria-label="Chart mode">
          <ToggleGroupItem value="daily" className="px-2.5 text-xs">Daily</ToggleGroupItem>
          <ToggleGroupItem value="cumulative" className="px-2.5 text-xs">Cumulative</ToggleGroupItem>
        </ToggleGroup>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-[240px] w-full" />
        ) : rows.length === 0 ? (
          <EmptyState icon={CalendarRangeIcon} title="No simulated days in this period yet." className="h-[240px] py-0" />
        ) : (
          <ChartContainer config={chartConfig} className="aspect-auto h-[240px] w-full">
            {mode === "daily" ? (
              <BarChart data={rows} margin={{ left: 4, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} strokeOpacity={0.4} />
                <XAxis dataKey="day" tickLine={false} axisLine={false} minTickGap={28} tickFormatter={shortDay} />
                <YAxis tickFormatter={(v) => money(v)} tickLine={false} axisLine={false} width={64} />
                <ReferenceLine y={0} stroke="var(--muted-foreground)" strokeOpacity={0.6} />
                {tooltip}
                <Bar dataKey="profit" radius={[3, 3, 3, 3]} maxBarSize={28}>
                  {rows.map((d) => (
                    <Cell key={d.day} fill={d.profit < 0 ? "var(--loss)" : "var(--profit)"} fillOpacity={d.closed ? 0.85 : 0.35} />
                  ))}
                </Bar>
              </BarChart>
            ) : (
              <AreaChart data={rows} margin={{ left: 4, right: 8, top: 8 }}>
                <defs>
                  <linearGradient id="g-cum" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-cumulative_profit)" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="var(--color-cumulative_profit)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} strokeOpacity={0.4} />
                <XAxis dataKey="day" tickLine={false} axisLine={false} minTickGap={28} tickFormatter={shortDay} />
                <YAxis tickFormatter={(v) => money(v)} tickLine={false} axisLine={false} width={64} />
                <ReferenceLine y={0} stroke="var(--muted-foreground)" strokeOpacity={0.6} />
                {tooltip}
                <Area dataKey="cumulative_profit" type="monotone" stroke="var(--color-cumulative_profit)" fill="url(#g-cum)" strokeWidth={2} isAnimationActive={false} />
              </AreaChart>
            )}
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}

export function DaysTable({ data }: { data: PeriodPnl | null }) {
  const router = useRouter()
  if (!data) return <Skeleton className="h-[520px] w-full" />
  const rows = [...data.daily].reverse()
  if (!rows.length) return <EmptyState icon={CalendarRangeIcon} title="No simulated days in this period yet." />
  return (
    <div className="max-h-[520px] overflow-auto rounded-lg border">
      <Table className="text-[13px]">
        <TableHeader className="sticky top-0 z-10 bg-background/95 backdrop-blur">
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-9">Day</TableHead>
            <TableHead className="text-right">Flights</TableHead>
            <TableHead className="hidden text-right 2xl:table-cell">Passengers</TableHead>
            <TableHead className="text-right">Load factor</TableHead>
            <TableHead className="text-right">Revenue</TableHead>
            <TableHead className="hidden text-right md:table-cell">
              <span className="inline-flex items-center gap-1">Cost <Est /></span>
            </TableHead>
            <TableHead className="text-right">
              <span className="inline-flex items-center gap-1">Profit <Est /></span>
            </TableHead>
            <TableHead className="text-right">Delayed</TableHead>
            <TableHead className="text-right">Cancelled</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((d) => (
            <TableRow
              key={d.day}
              tabIndex={0}
              onClick={() => router.push(`/pnl?day=${d.day}`)}
              onKeyDown={(e) => e.key === "Enter" && router.push(`/pnl?day=${d.day}`)}
              title="Open in Daily P&L"
              className={cn("h-10 cursor-pointer border-l-2 border-l-transparent focus-visible:bg-muted/50 focus-visible:outline-none", d.profit < 0 && "border-l-loss")}
            >
              <TableCell className="whitespace-nowrap">
                <span className="num text-muted-foreground">D{d.day_index}</span> {dayLabel(d.day)}
                {!d.closed ? <span className="ml-1.5 text-xs text-primary">live</span> : null}
              </TableCell>
              <TableCell className="num text-right">{d.flights}</TableCell>
              <TableCell className="num hidden text-right 2xl:table-cell">{int(d.pax)}</TableCell>
              <TableCell className="num text-right">{pct(d.load_factor)}</TableCell>
              <TableCell className="num text-right">{money(d.revenue)}</TableCell>
              <TableCell className="num hidden text-right md:table-cell">{money(d.cost_total)}</TableCell>
              <TableCell className="text-right">
                <Signed value={d.profit} format={(v) => money(v, { sign: true })} />
              </TableCell>
              <TableCell className={cn("num text-right", d.delayed ? "text-delayed" : "text-muted-foreground")}>{d.delayed}</TableCell>
              <TableCell className={cn("num text-right", d.cancelled ? "text-loss" : "text-muted-foreground")}>{d.cancelled}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
