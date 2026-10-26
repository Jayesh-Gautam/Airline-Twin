"use client"

import * as React from "react"
import { CloudLightningIcon, FlaskConicalIcon, ShuffleIcon, WrenchIcon } from "lucide-react"

import { useSim } from "@/components/sim-provider"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { api, qs, type Scenario } from "@/lib/api"
import { FUEL_DEFAULT } from "@/lib/constants"

type Ap = { iata: string; name: string; city: string }
type Ac = { id: number; registration: string; model: string; status: string }

const BASELINE: Scenario = {
  demand: 1,
  delay_multiplier: 1,
  fuel_price: FUEL_DEFAULT,
  bad_weather: { enabled: false, airports: [] },
  grounded_aircraft: [],
  real_life: false,
}

function Row({ label, value, children, hint }: { label: string; value: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="grid gap-3">
      <div className="flex items-baseline justify-between">
        <Label className="text-sm font-medium">{label}</Label>
        <span className="num text-sm">{value}</span>
      </div>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

export function ScenarioSheet() {
  const { state, airlineId, applyScenario, busy } = useSim()
  const [open, setOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<Scenario>(BASELINE)
  const [airports, setAirports] = React.useState<Ap[]>([])
  const [fleet, setFleet] = React.useState<Ac[]>([])

  React.useEffect(() => {
    if (!open) return
    if (state?.scenario) setDraft({ ...BASELINE, ...structuredClone(state.scenario) })
    const q = qs({ airline: airlineId })
    api<{ airports: Ap[] }>(`/airports${q}`).then((r) => setAirports(r.airports)).catch(() => setAirports([]))
    api<Ac[]>(`/sim/fleet${q}`).then(setFleet).catch(() => setFleet([]))
    // only when the sheet opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, airlineId])

  const changed = state ? JSON.stringify(draft) !== JSON.stringify(state.scenario) : false
  const active =
    !!state &&
    (state.scenario.demand !== 1 ||
      state.scenario.delay_multiplier !== 1 ||
      state.scenario.fuel_price !== FUEL_DEFAULT ||
      state.scenario.bad_weather.enabled ||
      state.scenario.grounded_aircraft.length > 0 ||
      state.scenario.real_life)

  const toggle = (list: string[] | number[], v: string | number) =>
    (list as (string | number)[]).includes(v) ? (list as (string | number)[]).filter((x) => x !== v) : [...list, v]

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <FlaskConicalIcon strokeWidth={1.5} />
          Scenario
          {active ? <span className="size-1.5 rounded-full bg-primary" aria-label="scenario active" /> : null}
        </Button>
      </SheetTrigger>
      <SheetContent className="flex w-full flex-col gap-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle>What-if scenario</SheetTitle>
          <SheetDescription>Changes apply from the current sim time onward and are logged as events.</SheetDescription>
        </SheetHeader>
        <ScrollArea className="min-h-0 flex-1">
          <div className="grid gap-7 p-4">
            <div className="grid gap-2 rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="real-life" className="flex items-center gap-2 text-sm font-medium">
                  <ShuffleIcon className="size-4" strokeWidth={1.5} /> Real-life mode
                </Label>
                <Switch id="real-life" checked={!!draft.real_life} onCheckedChange={(v) => setDraft({ ...draft, real_life: v })} />
              </div>
              <p className="text-xs text-muted-foreground">
                Conditions change randomly every day, like in reality: storms, snow and fog at airports, ATC strikes,
                seasonal demand with surges and slumps, a moving fuel price and unexpected technical faults. The sliders
                below still apply on top. Same seed, same story.
              </p>
            </div>
            <Row label="Demand level" value={`${Math.round(draft.demand * 100)}%`} hint="Scales passengers sampled from the historical load-factor distribution.">
              <Slider min={50} max={130} step={5} value={[Math.round(draft.demand * 100)]} onValueChange={([v]) => setDraft({ ...draft, demand: v / 100 })} aria-label="Demand level" />
            </Row>
            <Row label="Delay probability" value={`${draft.delay_multiplier.toFixed(1)}×`} hint="Multiplies the historical delay odds per route and airport.">
              <Slider min={0} max={3} step={0.1} value={[draft.delay_multiplier]} onValueChange={([v]) => setDraft({ ...draft, delay_multiplier: Math.round(v * 10) / 10 })} aria-label="Delay probability multiplier" />
            </Row>
            <Row label="Fuel price" value={`$${draft.fuel_price.toFixed(2)}/kg`} hint="Baseline 0.80 per kg (config.py). Applies to flights departing from now.">
              <Slider min={0.4} max={1.6} step={0.05} value={[draft.fuel_price]} onValueChange={([v]) => setDraft({ ...draft, fuel_price: Math.round(v * 100) / 100 })} aria-label="Fuel price" />
            </Row>
            <Separator />
            <div className="grid gap-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="wx" className="flex items-center gap-2 text-sm font-medium">
                  <CloudLightningIcon className="size-4" strokeWidth={1.5} /> Bad weather day
                </Label>
                <Switch id="wx" checked={draft.bad_weather.enabled} onCheckedChange={(v) => setDraft({ ...draft, bad_weather: { ...draft.bad_weather, enabled: v } })} />
              </div>
              <p className="text-xs text-muted-foreground">3× delay odds, 1.5× delay minutes and some cancellations at the chosen airports.</p>
              {draft.bad_weather.enabled ? (
                <div className="grid max-h-44 grid-cols-3 gap-1.5 overflow-y-auto rounded-lg border p-2">
                  {airports.map((a) => (
                    <label key={a.iata} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted" title={`${a.name}, ${a.city}`}>
                      <Checkbox checked={draft.bad_weather.airports.includes(a.iata)} onCheckedChange={() => setDraft({ ...draft, bad_weather: { ...draft.bad_weather, airports: toggle(draft.bad_weather.airports, a.iata) as string[] } })} />
                      <span className="num">{a.iata}</span>
                    </label>
                  ))}
                </div>
              ) : null}
            </div>
            <Separator />
            <div className="grid gap-3">
              <Label className="flex items-center gap-2 text-sm font-medium">
                <WrenchIcon className="size-4" strokeWidth={1.5} /> Aircraft grounded
              </Label>
              <p className="text-xs text-muted-foreground">A grounded aircraft cannot fly; its flights get a tail swap, a delay or a cancellation.</p>
              <div className="grid max-h-52 gap-1 overflow-y-auto rounded-lg border p-2">
                {fleet.length === 0 ? <span className="px-1.5 py-1 text-sm text-muted-foreground">Loading fleet…</span> : null}
                {fleet.map((a) => (
                  <label key={a.id} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted">
                    <Checkbox checked={draft.grounded_aircraft.includes(a.id)} onCheckedChange={() => setDraft({ ...draft, grounded_aircraft: toggle(draft.grounded_aircraft, a.id) as number[] })} />
                    <span className="num w-16">{a.registration}</span>
                    <span className="text-muted-foreground">{a.model}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{a.status}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </ScrollArea>
        <SheetFooter className="flex-row border-t">
          <Button variant="ghost" onClick={() => setDraft(structuredClone(BASELINE))}>Baseline</Button>
          <Button className="ml-auto" disabled={!changed || busy} onClick={async () => { await applyScenario(draft); setOpen(false) }}>
            Apply from now
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
