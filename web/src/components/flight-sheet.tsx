"use client"

import { Est, Label12, Signed, StatusBadge } from "@/components/bits"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import type { Flight } from "@/lib/api"
import { airlineColor } from "@/lib/airlines"
import { duration, hhmm, int, money, pct } from "@/lib/format"

function KV({ k, v, est }: { k: string; v: React.ReactNode; est?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5 text-sm">
      <span className="flex items-center gap-1.5 text-muted-foreground">
        {k}
        {est ? <Est /> : null}
      </span>
      <span className="num text-right">{v}</span>
    </div>
  )
}

export function FlightDetail({ f }: { f: Flight }) {
  const done = f.status === "Landed" || f.status === "Cancelled"
  const progress = f.position?.progress ?? (f.status === "Landed" ? 1 : 0)
  return (
    <div className="grid gap-5 p-4">
      <div className="grid gap-2">
        <div className="flex items-center justify-between">
          <StatusBadge status={f.status} delayed={f.delay_minutes >= 15} />
          <span className="num text-xs text-muted-foreground">{int(f.distance_km)} km · {duration(f.block_h * 60)} block</span>
        </div>
        <Progress value={progress * 100} className="h-1.5" aria-label="Flight progress" />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span className="num">{f.origin} {hhmm(f.atd ?? f.etd)}</span>
          <span className="num">{hhmm(f.ata ?? f.eta)} {f.destination}</span>
        </div>
      </div>

      <div>
        <Label12>Schedule (UTC)</Label12>
        <KV k="STD → ETD" v={`${hhmm(f.std)} → ${hhmm(f.etd)}`} />
        <KV k="STA → ETA" v={`${hhmm(f.sta)} → ${hhmm(f.eta)}`} />
        <KV k="Delay" v={f.delay_minutes ? `${duration(f.delay_minutes)} · ${f.delay_reason ?? ""}` : "On time"} />
        {f.cancel_reason ? <KV k="Cancelled" v={<span className="text-loss">{f.cancel_reason}</span>} /> : null}
      </div>
      <Separator />
      <div>
        <Label12>Aircraft & load</Label12>
        <KV k="Aircraft" v={`${f.registration} · ${f.model}`} />
        <KV k="Passengers / seats" v={`${int(f.pax)} / ${int(f.capacity)}`} />
        <KV k="Load factor" v={pct(f.load_factor)} />
        <KV k="Break-even load factor" v={f.break_even_lf != null ? pct(f.break_even_lf) : "–"} est />
        <KV k="Fuel burn" v={`${int(f.fuel_kg_est)} kg`} est />
      </div>
      <Separator />
      <div>
        <Label12>Money</Label12>
        <KV k="Revenue (booked at departure)" v={money(f.revenue)} />
        <KV k="Cost so far" v={money(f.cost_so_far)} est />
        <KV k="Profit so far" v={<Signed value={f.profit_so_far} format={(v) => money(v, { sign: true })} />} est />
        {!done ? <KV k="Projected result" v={<Signed value={f.profit_projected} format={(v) => money(v, { sign: true })} />} est /> : null}
        {f.revenue_lost ? <KV k="Revenue lost (refunded)" v={<span className="text-loss">{money(-f.revenue_lost)}</span>} /> : null}
      </div>
    </div>
  )
}

export function FlightSheet({ flight, onClose }: { flight: Flight | null; onClose: () => void }) {
  return (
    <Sheet open={!!flight} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-md" onOpenAutoFocus={(e) => e.preventDefault()}>
        {flight ? (
          <>
            <SheetHeader className="border-b">
              <SheetTitle className="flex items-center gap-2">
                <span className="size-2 rounded-full" style={{ background: airlineColor(flight.airline_id) }} aria-hidden />
                <span className="num">{flight.flight_number}</span>
                <span className="text-muted-foreground">{flight.origin} → {flight.destination}</span>
              </SheetTitle>
              <SheetDescription>
                {flight.airline} (fictional) · {flight.is_ferry ? "repositioning flight" : "scheduled service"} · simulated
              </SheetDescription>
            </SheetHeader>
            <FlightDetail f={flight} />
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  )
}
