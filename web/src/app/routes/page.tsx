"use client"

import * as React from "react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { PlaneIcon, RouteIcon } from "lucide-react"

import { EmptyState, Est, PageHeader, Signed } from "@/components/bits"
import { useSim } from "@/components/sim-provider"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api, qs } from "@/lib/api"
import { airlineColor } from "@/lib/airlines"
import { int, money, pct } from "@/lib/format"
import { cn } from "@/lib/utils"

type SimRoute = {
  airline_id: number
  airline: string
  route: string
  distance_km: number
  flights: number
  cancelled: number
  delayed: number
  load_factor: number | null
  break_even_lf: number | null
  revenue: number
  profit: number
  margin: number | null
  historical: { departures: number; avg_load_factor: number; revenue: number; profit_est: number; margin_est: number } | null
}

type Aircraft = {
  id: number
  registration: string
  model: string
  capacity: number
  airline_id: number
  airline: string
  status: string
  location: string
  flights: number
  block_hours: number
  crew_cost_est: number
  revenue: number
  maintenance: { type: string; until: string } | null
  next_maintenance: { type: string; start: string } | null
  maintenance_cost_est: number
}

const FLEET_STATUS: Record<string, string> = {
  "In Flight": "text-foreground",
  "On ground": "text-muted-foreground",
  Maintenance: "text-delayed",
  Grounded: "text-loss",
}
const FLEET_DOT: Record<string, string> = {
  "In Flight": "bg-profit",
  "On ground": "bg-neutral-status",
  Maintenance: "bg-delayed",
  Grounded: "bg-loss",
}

export default function RoutesFleetPage() {
  const { airlineId, state } = useSim()
  const [routes, setRoutes] = React.useState<SimRoute[] | null>(null)
  const [fleet, setFleet] = React.useState<Aircraft[] | null>(null)
  const tick = state ? `${state.day}|${state.clock.slice(11, 13)}` : null

  React.useEffect(() => {
    api<SimRoute[]>(`/sim/routes${qs({ airline: airlineId })}`).then(setRoutes).catch(() => setRoutes([]))
    api<Aircraft[]>(`/sim/fleet${qs({ airline: airlineId })}`).then(setFleet).catch(() => setFleet([]))
  }, [airlineId, tick])

  const flown = routes?.filter((r) => r.flights > 0) ?? []
  const util = (fleet ?? []).map((a) => ({ reg: a.registration, hours: a.block_hours, id: a.airline_id }))
  const utilConfig = { hours: { label: "Block hours", color: "var(--chart-1)" } } satisfies ChartConfig

  return (
    <div className="grid gap-4">
      <PageHeader title="Routes & Fleet" description="Simulated route economics next to the historical Spark results, and how hard each aircraft is working." />
      <Tabs defaultValue="routes" className="gap-4">
        <TabsList>
          <TabsTrigger value="routes">Routes</TabsTrigger>
          <TabsTrigger value="fleet">Fleet</TabsTrigger>
        </TabsList>

        <TabsContent value="routes">
          <Card className="gap-3 rounded-xl shadow-none">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm font-medium">Route profitability: simulated vs historical <Est /></CardTitle>
              <CardDescription>Simulated = all days run so far. Historical = PySpark analysis of 2021–2025 (a_route_profitability). Routes marked “return” are mirrored legs the source data does not list.</CardDescription>
            </CardHeader>
            <CardContent>
              {!routes ? (
                <Skeleton className="h-96 w-full" />
              ) : flown.length === 0 ? (
                <EmptyState icon={RouteIcon} title="No routes flown yet. Start the simulation." />
              ) : (
                <div className="max-h-[640px] overflow-auto rounded-lg border">
                  <Table className="text-[13px]">
                    <TableHeader className="sticky top-0 z-10 bg-background/95 backdrop-blur">
                      <TableRow className="hover:bg-transparent">
                        <TableHead>Route</TableHead>
                        <TableHead className="text-right">km</TableHead>
                        <TableHead className="border-l text-right">Sim flights</TableHead>
                        <TableHead className="text-right">Load factor</TableHead>
                        <TableHead className="text-right">Break-even</TableHead>
                        <TableHead className="text-right">Profit</TableHead>
                        <TableHead className="text-right">Margin</TableHead>
                        <TableHead className="border-l text-right">Hist. departures</TableHead>
                        <TableHead className="text-right">Hist. load factor</TableHead>
                        <TableHead className="text-right">Hist. margin</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {flown.map((r) => (
                        <TableRow key={`${r.airline_id}${r.route}`} className={cn("h-10 border-l-2 border-l-transparent", r.profit < 0 && "border-l-loss")}>
                          <TableCell>
                            <span className="flex items-center gap-2">
                              <span className="size-2 rounded-full" style={{ background: airlineColor(r.airline_id) }} aria-label={r.airline} />
                              <span className="num font-medium">{r.route}</span>
                              {!r.historical ? <Badge variant="outline" className="h-4 px-1 text-[10px] font-normal text-muted-foreground">return</Badge> : null}
                            </span>
                          </TableCell>
                          <TableCell className="num text-right text-muted-foreground">{int(r.distance_km)}</TableCell>
                          <TableCell className="num border-l text-right">{r.flights}{r.cancelled ? <span className="text-loss"> +{r.cancelled}✕</span> : null}</TableCell>
                          <TableCell className={cn("num text-right", r.load_factor != null && r.break_even_lf != null && r.load_factor < r.break_even_lf && "text-loss")}>{pct(r.load_factor)}</TableCell>
                          <TableCell className="num text-right text-muted-foreground">{pct(r.break_even_lf)}</TableCell>
                          <TableCell className="text-right"><Signed value={r.profit} format={(v) => money(v, { sign: true })} /></TableCell>
                          <TableCell className="num text-right">{pct(r.margin)}</TableCell>
                          <TableCell className="num border-l text-right text-muted-foreground">{r.historical ? int(r.historical.departures) : "–"}</TableCell>
                          <TableCell className="num text-right text-muted-foreground">{r.historical ? pct(r.historical.avg_load_factor) : "–"}</TableCell>
                          <TableCell className="num text-right text-muted-foreground">{r.historical ? pct(r.historical.margin_est) : "–"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="fleet" className="grid gap-4">
          <Card className="gap-2 rounded-xl shadow-none">
            <CardHeader>
              <CardTitle className="text-sm font-medium">Block hours flown per aircraft (simulated)</CardTitle>
            </CardHeader>
            <CardContent>
              {fleet ? (
                <ChartContainer config={utilConfig} className="aspect-auto h-[200px] w-full">
                  <BarChart data={util} margin={{ left: 4, right: 8, top: 8 }}>
                    <CartesianGrid vertical={false} strokeOpacity={0.4} />
                    <XAxis dataKey="reg" tickLine={false} axisLine={false} interval={0} angle={-45} textAnchor="end" height={50} className="num" />
                    <YAxis tickLine={false} axisLine={false} width={40} />
                    <ChartTooltip cursor={{ fill: "var(--muted)", opacity: 0.4 }} content={<ChartTooltipContent hideIndicator />} />
                    <Bar dataKey="hours" fill="var(--color-hours)" radius={[4, 4, 0, 0]} maxBarSize={28} />
                  </BarChart>
                </ChartContainer>
              ) : (
                <Skeleton className="h-[200px] w-full" />
              )}
            </CardContent>
          </Card>
          <Card className="gap-3 rounded-xl shadow-none">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm font-medium">Fleet status, utilisation and costs <Est /></CardTitle>
            </CardHeader>
            <CardContent>
              {!fleet ? (
                <Skeleton className="h-96 w-full" />
              ) : fleet.length === 0 ? (
                <EmptyState icon={PlaneIcon} title="No aircraft for this airline." />
              ) : (
                <div className="max-h-[560px] overflow-auto rounded-lg border">
                  <Table className="text-[13px]">
                    <TableHeader className="sticky top-0 z-10 bg-background/95 backdrop-blur">
                      <TableRow className="hover:bg-transparent">
                        <TableHead>Aircraft</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Where</TableHead>
                        <TableHead className="text-right">Flights</TableHead>
                        <TableHead className="text-right">Block hours</TableHead>
                        <TableHead className="text-right">Revenue</TableHead>
                        <TableHead className="text-right">Crew cost</TableHead>
                        <TableHead className="text-right">Maintenance</TableHead>
                        <TableHead>Next check</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {fleet.map((a) => (
                        <TableRow key={a.id} className="h-10">
                          <TableCell>
                            <span className="flex items-center gap-2">
                              <span className="size-2 rounded-full" style={{ background: airlineColor(a.airline_id) }} aria-label={a.airline} />
                              <span className="num font-medium">{a.registration}</span>
                              <span className="text-muted-foreground">{a.model} · {a.capacity}</span>
                            </span>
                          </TableCell>
                          <TableCell>
                            <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", FLEET_STATUS[a.status])}>
                              <span className={cn("size-1.5 rounded-full", FLEET_DOT[a.status])} aria-hidden />
                              {a.status}
                            </span>
                          </TableCell>
                          <TableCell className="num text-muted-foreground">{a.maintenance ? `${a.maintenance.type} until ${a.maintenance.until.slice(5, 16).replace("T", " ")}` : a.location}</TableCell>
                          <TableCell className="num text-right">{a.flights}</TableCell>
                          <TableCell className="num text-right">{a.block_hours.toFixed(1)}</TableCell>
                          <TableCell className="num text-right">{money(a.revenue)}</TableCell>
                          <TableCell className="num text-right">{money(a.crew_cost_est)}</TableCell>
                          <TableCell className="num text-right">{money(a.maintenance_cost_est)}</TableCell>
                          <TableCell className="num text-muted-foreground">{a.next_maintenance ? `${a.next_maintenance.type} ${a.next_maintenance.start.slice(5, 10)}` : "–"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
