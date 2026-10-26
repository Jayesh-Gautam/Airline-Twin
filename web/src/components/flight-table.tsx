"use client"

import * as React from "react"
import { PlaneIcon, SearchIcon } from "lucide-react"

import { EmptyState, Est, Signed, StatusBadge } from "@/components/bits"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Flight } from "@/lib/api"
import { duration, hhmm, money } from "@/lib/format"
import { cn } from "@/lib/utils"

const STATUSES = ["All", "Scheduled", "Boarding", "Delayed", "Departed", "In Flight", "Landed", "Cancelled"]

export function FlightTable({
  flights,
  onSelect,
  maxHeight = 520,
  empty,
}: {
  flights: Flight[]
  onSelect: (f: Flight) => void
  maxHeight?: number
  empty?: React.ReactNode
}) {
  const [q, setQ] = React.useState("")
  const [status, setStatus] = React.useState("All")
  const rows = React.useMemo(() => {
    const s = q.trim().toLowerCase()
    return flights.filter(
      (f) =>
        (status === "All" || f.status === status || (status === "Delayed" && f.delay_minutes >= 15 && f.status !== "Cancelled")) &&
        (!s || `${f.flight_number} ${f.route} ${f.registration} ${f.model}`.toLowerCase().includes(s))
    )
  }, [flights, q, status])

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" strokeWidth={1.5} />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search flight, route, aircraft" className="h-8 pl-8" aria-label="Search flights" />
        </div>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger size="sm" className="w-36" aria-label="Status filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {s === "All" ? "All statuses" : s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="num text-xs text-muted-foreground">{rows.length} flights</span>
      </div>
      <div className="overflow-auto rounded-lg border" style={{ maxHeight }}>
        <Table className="text-[13px]">
          <TableHeader className="sticky top-0 z-10 bg-background/95 backdrop-blur">
            <TableRow className="hover:bg-transparent">
              <TableHead className="h-9">Flight</TableHead>
              <TableHead>Route</TableHead>
              <TableHead className="hidden 2xl:table-cell">Aircraft</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">STD / ETD</TableHead>
              <TableHead className="text-right">STA / ETA</TableHead>
              <TableHead className="hidden text-right md:table-cell">Delay</TableHead>
              <TableHead className="hidden text-right md:table-cell">Pax / seats</TableHead>
              <TableHead className="text-right">
                <span className="inline-flex items-center gap-1">Profit <Est /></span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((f) => {
              const late = f.delay_minutes >= 15
              const loss = f.status !== "Cancelled" && !f.is_ferry && (f.status === "Landed" ? f.profit_so_far : f.profit_projected) < 0
              return (
                <TableRow
                  key={f.id}
                  onClick={() => onSelect(f)}
                  onKeyDown={(e) => e.key === "Enter" && onSelect(f)}
                  tabIndex={0}
                  className={cn(
                    "h-10 cursor-pointer border-l-2 border-l-transparent focus-visible:bg-muted/50 focus-visible:outline-none",
                    (loss || f.status === "Cancelled") && "border-l-loss"
                  )}
                >
                  <TableCell className="num font-medium">{f.flight_number}</TableCell>
                  <TableCell className="num">{f.origin}–{f.destination}</TableCell>
                  <TableCell className="hidden text-muted-foreground 2xl:table-cell">
                    <span className="num">{f.registration}</span> · {f.model}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={f.status} delayed={late} />
                  </TableCell>
                  <TableCell className="num text-right">
                    {late ? <span className="text-muted-foreground line-through">{hhmm(f.std)}</span> : hhmm(f.std)}
                    {late ? <span className="ml-1.5 text-delayed">{hhmm(f.etd)}</span> : null}
                  </TableCell>
                  <TableCell className="num text-right">{hhmm(f.ata ?? f.eta)}</TableCell>
                  <TableCell className={cn("num hidden text-right md:table-cell", late ? "text-delayed" : "text-muted-foreground")}>
                    {f.status === "Cancelled" ? "–" : late ? duration(f.delay_minutes) : "—"}
                  </TableCell>
                  <TableCell className="num hidden text-right md:table-cell">
                    {f.is_ferry ? <span className="text-muted-foreground">ferry</span> : `${f.pax}/${f.capacity}`}
                  </TableCell>
                  <TableCell className="text-right">
                    {f.status === "Scheduled" || f.status === "Boarding" || f.status === "Delayed" ? (
                      <span className="num text-muted-foreground">{money(f.profit_projected, { sign: true })}</span>
                    ) : (
                      <Signed value={f.profit_so_far} format={(v) => money(v, { sign: true })} />
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
        {rows.length === 0 ? empty ?? <EmptyState icon={PlaneIcon} title="No flights match this filter." /> : null}
      </div>
    </div>
  )
}
