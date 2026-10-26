"use client"

import { CloudLightningIcon, RadioTowerIcon, ShuffleIcon, TrendingUpIcon, WrenchIcon, type LucideIcon } from "lucide-react"

import { Label12 } from "@/components/bits"
import { useSim } from "@/components/sim-provider"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import type { Condition } from "@/lib/api"
import { hhmm } from "@/lib/format"
import { cn } from "@/lib/utils"

const ICON: Record<Condition["kind"], LucideIcon> = {
  weather: CloudLightningIcon,
  atc: RadioTowerIcon,
  demand: TrendingUpIcon,
  aog: WrenchIcon,
}

function Item({ c, upcoming }: { c: Condition; upcoming?: boolean }) {
  const Icon = ICON[c.kind] ?? CloudLightningIcon
  return (
    <li className="flex items-start gap-2 py-1.5 text-sm">
      <Icon className={cn("mt-0.5 size-3.5 shrink-0", upcoming ? "text-muted-foreground" : "text-delayed")} strokeWidth={1.5} />
      <span className="min-w-0 flex-1">{c.label}</span>
      <span className="num shrink-0 text-xs text-muted-foreground">
        {upcoming ? `from ${hhmm(c.start)}` : c.end.slice(0, 10) === c.start.slice(0, 10) ? `to ${hhmm(c.end)}` : `to ${c.end.slice(5, 10)}`}
      </span>
    </li>
  )
}

/** Shown in the top bar while real-life mode is on: today's random conditions. */
export function ConditionsIndicator() {
  const { state } = useSim()
  const c = state?.conditions
  if (!c?.enabled) return null
  const delta = (v: number) => `${v >= 1 ? "+" : "−"}${Math.abs((v - 1) * 100).toFixed(0)}%`
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5" aria-label="Real-life conditions">
          <ShuffleIcon strokeWidth={1.5} />
          <span className="hidden lg:inline">Real-life</span>
          {c.active.length ? (
            <span className="num rounded bg-delayed/15 px-1 text-xs text-delayed">{c.active.length}</span>
          ) : (
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60" />
              <span className="relative inline-flex size-1.5 rounded-full bg-primary" />
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <p className="text-sm font-medium">Real-life conditions</p>
        <p className="mb-3 text-xs text-muted-foreground">Random, like reality; reproducible with the seed. Values include your sliders.</p>
        <div className="grid grid-cols-3 gap-2 rounded-lg border p-2.5">
          <div>
            <Label12 className="text-[10px]">Fuel</Label12>
            <p className="num text-sm">${c.fuel_price.toFixed(2)}/kg</p>
          </div>
          <div>
            <Label12 className="text-[10px]">Demand</Label12>
            <p className={cn("num text-sm", c.demand < 0.97 ? "text-loss" : c.demand > 1.03 ? "text-profit" : "")}>{delta(c.demand)}</p>
          </div>
          <div>
            <Label12 className="text-[10px]">Delay odds</Label12>
            <p className={cn("num text-sm", c.delay_index > 1.1 ? "text-delayed" : "")}>{c.delay_index.toFixed(2)}×</p>
          </div>
        </div>
        <div className="mt-3">
          <Label12 className="text-[10px]">Now</Label12>
          {c.active.length ? <ul className="divide-y">{c.active.map((x, i) => <Item key={i} c={x} />)}</ul> : <p className="py-1.5 text-sm text-muted-foreground">No disruptions right now.</p>}
        </div>
        {c.upcoming.length ? (
          <div className="mt-2">
            <Label12 className="text-[10px]">Later today</Label12>
            <ul className="divide-y">{c.upcoming.map((x, i) => <Item key={i} c={x} upcoming />)}</ul>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}
