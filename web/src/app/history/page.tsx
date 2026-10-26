"use client"

import * as React from "react"
import { Area, AreaChart, Bar, BarChart, CartesianGrid, LabelList, ReferenceLine, XAxis, YAxis } from "recharts"
import { CpuIcon } from "lucide-react"

import { Est, Label12, PageHeader } from "@/components/bits"
import { KpiCard } from "@/components/kpi-card"
import { useSim } from "@/components/sim-provider"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, qs } from "@/lib/api"
import { int, money, pct } from "@/lib/format"
import { cn } from "@/lib/utils"

type Summary = {
  departures: number
  passengers: number
  fare_revenue: number
  operating_profit_est: number
  delay_rate: number | null
  avg_load_factor: number
  routes: number
  pipeline: { timings_s?: Record<string, number>; data_quality?: Record<string, number | string>; spark_version?: string }
}
type Month = { year_month: string; fare_revenue: number; operating_profit_est: number; departures: number }
type Delays = { by_reason: { reason: string; delays: number; avg_minutes: number }[]; by_airport: { airport: string; departures: number; delay_rate: number }[] }
type Fuel = { model: string; capacity: number; departures: number; kg_per_seat_hour_est: number; fuel_cost_per_passenger_est: number | null }
type Cabin = { cabin: string; revenue_share: number; avg_fare: number; segments: number }
type QualityRun = { run: { run: string; data_quality: Record<string, number | string>; timings_s: Record<string, number> }; tables: unknown[] } | null
type Quality = { clean: QualityRun; dirty: QualityRun }

function useApi<T>(path: string) {
  const [d, setD] = React.useState<T | null>(null)
  React.useEffect(() => {
    setD(null)
    api<T>(path).then(setD).catch(() => setD(null))
  }, [path])
  return d
}

const trendConfig = {
  fare_revenue: { label: "Fare revenue", color: "var(--chart-1)" },
  operating_profit_est: { label: "Operating profit (est.)", color: "var(--chart-2)" },
} satisfies ChartConfig

const QUALITY_ROWS: [string, string][] = [
  ["rows_raw", "Rows in"],
  ["rows_clean", "Rows out"],
  ["exact_duplicates", "Exact duplicates removed"],
  ["near_duplicates", "Near duplicates removed"],
  ["category_values_repaired", "Typos repaired"],
  ["outliers_nulled", "Outliers set to NULL"],
  ["orphan_rows_removed", "Orphaned rows removed"],
  ["unparsed_dates", "Unparsed dates"],
  ["fares_imputed", "Fares imputed"],
  ["payments_repaired", "Payments recomputed"],
]

export default function HistoryPage() {
  const { airlineId, airline } = useSim()
  const q = qs({ airline: airlineId })
  const summary = useApi<Summary>(`/history/summary${q}`)
  const monthly = useApi<Month[]>(`/history/monthly${q}`)
  const delays = useApi<Delays>(`/history/delays${q}`)
  const fuel = useApi<Fuel[]>(`/history/fuel${q}`)
  const cabins = useApi<Cabin[]>(`/history/cabins`)
  const quality = useApi<Quality>(`/history/quality`)
  const rows = Number(summary?.pipeline?.data_quality?.rows_clean ?? 0)
  const t = summary?.pipeline?.timings_s

  return (
    <div className="grid gap-4">
      <PageHeader
        title="Historical Analytics"
        description={airline ? `${airline.name} (fictional), 2021–2025` : "All six fictional airlines, 2021–2025"}
      >
        <Badge variant="outline" className="h-7 gap-1.5 px-2.5 font-normal">
          <CpuIcon className="size-3.5" strokeWidth={1.5} />
          Computed by PySpark from {rows ? `${(rows / 1e6).toFixed(2)}M` : "…"} rows
          {t ? <span className="num text-muted-foreground">· {Math.round(Object.values(t).reduce((a, b) => a + b, 0))} s</span> : null}
        </Badge>
      </PageHeader>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
        <KpiCard label="Departures" value={summary?.departures ?? null} format={int} />
        <KpiCard label="Passengers" value={summary?.passengers ?? null} format={int} />
        <KpiCard label="Fare revenue" value={summary?.fare_revenue ?? null} format={money} />
        <KpiCard label="Operating profit" estimate tone="auto" value={summary?.operating_profit_est ?? null} format={(v) => money(v, { sign: true })} footer="before maintenance" />
        <KpiCard label="Delay rate" value={summary?.delay_rate ?? null} format={(v) => pct(v)} footer="15 min or more" />
        <KpiCard label="Avg load factor" value={summary?.avg_load_factor ?? null} format={(v) => pct(v)} footer={summary ? `${summary.routes} routes` : ""} />
      </div>

      <Card className="gap-2 rounded-xl shadow-none">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm font-medium">Monthly fare revenue and operating profit <Est /></CardTitle>
          <CardDescription>MongoDB aggregation on flight_ops ($group by year_month), the table Spark built.</CardDescription>
        </CardHeader>
        <CardContent>
          {monthly ? (
            <ChartContainer config={trendConfig} className="aspect-auto h-[260px] w-full">
              <AreaChart data={monthly} margin={{ left: 4, right: 8, top: 8 }}>
                <defs>
                  {Object.keys(trendConfig).map((k) => (
                    <linearGradient key={k} id={`g-${k}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={`var(--color-${k})`} stopOpacity={0.25} />
                      <stop offset="100%" stopColor={`var(--color-${k})`} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid vertical={false} strokeOpacity={0.4} />
                <XAxis dataKey="year_month" tickLine={false} axisLine={false} interval={11} tickFormatter={(v: string) => v.slice(0, 4)} className="num" />
                <YAxis tickFormatter={(v) => money(v)} tickLine={false} axisLine={false} width={64} />
                <ReferenceLine y={0} stroke="var(--border)" />
                <ChartTooltip content={<ChartTooltipContent formatter={(v, n) => (
                  <div className="flex w-full justify-between gap-6"><span className="text-muted-foreground">{trendConfig[n as keyof typeof trendConfig]?.label}</span><span className="num">{money(Number(v))}</span></div>
                )} />} />
                <ChartLegend content={<ChartLegendContent />} />
                <Area dataKey="fare_revenue" type="monotone" stroke="var(--color-fare_revenue)" fill="url(#g-fare_revenue)" strokeWidth={1.5} />
                <Area dataKey="operating_profit_est" type="monotone" stroke="var(--color-operating_profit_est)" fill="url(#g-operating_profit_est)" strokeWidth={1.5} />
              </AreaChart>
            </ChartContainer>
          ) : (
            <Skeleton className="h-[260px] w-full" />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <HBar
          title="Delays by reason"
          description="Departures delayed 15 minutes or more"
          data={delays?.by_reason.map((r) => ({ name: r.reason, value: r.delays, note: `${r.avg_minutes} min avg` }))}
          format={int}
        />
        <HBar
          title="Worst origin airports for delays"
          description="Share of departures delayed (airports with 20+ departures)"
          data={delays?.by_airport.map((r) => ({ name: r.airport, value: r.delay_rate, note: `${r.departures} dep.` }))}
          format={(v) => pct(v)}
          mono
        />
        <HBar
          title="Fuel efficiency by aircraft model"
          estimate
          description="kg of fuel per seat per block hour (assumed burn rates, config.py)"
          data={fuel?.map((r) => ({ name: `${r.model} (${r.capacity})`, value: r.kg_per_seat_hour_est, note: r.fuel_cost_per_passenger_est != null ? `${money(r.fuel_cost_per_passenger_est)}/pax` : "" }))}
          format={(v) => v.toFixed(1)}
        />
        <HBar
          title="Cabin revenue share"
          description="Network-wide, from 1M ticket segments"
          data={cabins?.map((r) => ({ name: r.cabin, value: r.revenue_share, note: `avg ${money(r.avg_fare)}` }))}
          format={(v) => pct(v)}
        />
      </div>

      <Card className="gap-3 rounded-xl shadow-none">
        <CardHeader>
          <CardTitle className="text-sm font-medium">Data quality: what the Spark cleaning stage did</CardTitle>
          <CardDescription>The clean 1M dataset shows no false positives; the 100K dirty copy has faults planted by the dataset authors.</CardDescription>
        </CardHeader>
        <CardContent>
          {!quality ? (
            <Skeleton className="h-72 w-full" />
          ) : (
            <div className="overflow-auto rounded-lg border">
              <Table className="text-[13px]">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Check</TableHead>
                    <TableHead className="text-right">Clean {quality.clean?.run.run ?? ""}</TableHead>
                    <TableHead className="text-right">Dirty {quality.dirty?.run.run ?? "(not run)"}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {QUALITY_ROWS.map(([k, label]) => {
                    const c = quality.clean?.run.data_quality?.[k]
                    const d = quality.dirty?.run.data_quality?.[k]
                    return (
                      <TableRow key={k} className="h-10">
                        <TableCell>{label}</TableCell>
                        <TableCell className="num text-right">{c != null ? int(Number(c)) : "–"}</TableCell>
                        <TableCell className={cn("num text-right", k !== "rows_raw" && k !== "rows_clean" && Number(d) > 0 && "text-delayed")}>{d != null ? int(Number(d)) : "–"}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
          {t ? (
            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted-foreground">
              <Label12>Spark run</Label12>
              {Object.entries(t).map(([k, v]) => (
                <span key={k}>
                  {k.replace(/_/g, " ")} <span className="num text-foreground">{v.toFixed(1)} s</span>
                </span>
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}

function HBar({
  title,
  description,
  data,
  format,
  estimate,
  mono,
}: {
  title: string
  description: string
  data: { name: string; value: number; note?: string }[] | undefined
  format: (v: number) => string
  estimate?: boolean
  mono?: boolean
}) {
  const config = { value: { label: title, color: "var(--chart-1)" } } satisfies ChartConfig
  return (
    <Card className="gap-2 rounded-xl shadow-none">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-medium">{title} {estimate ? <Est /> : null}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-[240px] w-full" />
        ) : (
          <ChartContainer config={config} className="aspect-auto w-full" style={{ height: Math.max(160, data.length * 30 + 20) }}>
            <BarChart data={data} layout="vertical" margin={{ left: 0, right: 48 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" tickLine={false} axisLine={false} width={130} className={mono ? "num" : undefined} />
              <ChartTooltip cursor={{ fill: "var(--muted)", opacity: 0.4 }} content={<ChartTooltipContent hideIndicator formatter={(v, _n, item) => (
                <div className="flex w-full justify-between gap-6"><span className="num">{format(Number(v))}</span><span className="text-muted-foreground">{(item.payload as { note?: string }).note}</span></div>
              )} />} />
              <Bar dataKey="value" fill="var(--color-value)" radius={4} maxBarSize={18}>
                <LabelList dataKey="value" position="right" offset={8} formatter={(v: unknown) => format(Number(v))} fill="var(--muted-foreground)" fontSize={11} fontFamily="var(--font-geist-mono)" />
              </Bar>
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
