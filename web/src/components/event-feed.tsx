"use client"

import * as React from "react"
import { AnimatePresence, motion } from "motion/react"
import {
  ArrowRightLeftIcon,
  CircleXIcon,
  ClockAlertIcon,
  CloudLightningIcon,
  FlaskConicalIcon,
  ListIcon,
  MoveRightIcon,
  PlaneLandingIcon,
  PlaneTakeoffIcon,
  PlaneIcon,
  TrendingDownIcon,
  WrenchIcon,
  type LucideIcon,
} from "lucide-react"

import { EmptyState } from "@/components/bits"
import { useSim } from "@/components/sim-provider"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { api, qs, type SimEvent } from "@/lib/api"
import { hhmm, money } from "@/lib/format"
import { cn } from "@/lib/utils"

function iconFor(e: SimEvent): { icon: LucideIcon; tone: string } {
  switch (e.kind) {
    case "delay":
      return { icon: ClockAlertIcon, tone: "text-delayed" }
    case "cancel":
      return { icon: CircleXIcon, tone: "text-loss" }
    case "loss":
      return { icon: TrendingDownIcon, tone: "text-loss" }
    case "maintenance":
      return { icon: WrenchIcon, tone: "text-muted-foreground" }
    case "scenario":
      return { icon: FlaskConicalIcon, tone: "text-primary" }
    case "disruption":
      return { icon: CloudLightningIcon, tone: "text-delayed" }
    case "swap":
      return { icon: ArrowRightLeftIcon, tone: "text-muted-foreground" }
    case "reposition":
      return { icon: MoveRightIcon, tone: "text-muted-foreground" }
    default:
      if (e.status === "Departed") return { icon: PlaneTakeoffIcon, tone: "text-muted-foreground" }
      if (e.status === "Landed") return { icon: PlaneLandingIcon, tone: "text-muted-foreground" }
      return { icon: PlaneIcon, tone: "text-muted-foreground" }
  }
}

function EventRow({ e, animate }: { e: SimEvent; animate?: boolean }) {
  const { icon: Icon, tone } = iconFor(e)
  const Comp = animate ? motion.li : "li"
  const motionProps = animate
    ? { layout: "position" as const, initial: { opacity: 0, y: -6 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2 } }
    : {}
  return (
    <Comp {...motionProps} className="flex items-start gap-3 py-2">
      <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md border bg-muted/30", tone)}>
        <Icon className="size-3.5" strokeWidth={1.5} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm" title={e.text}>{e.text}</p>
        <p className="num text-xs text-muted-foreground">D{e.day_index} {hhmm(e.time)}</p>
      </div>
      {e.amount != null ? (
        <span className={cn("num shrink-0 text-sm", e.amount < 0 ? "text-loss" : "text-profit")}>{money(e.amount, { sign: true })}</span>
      ) : null}
    </Comp>
  )
}

/** Hide routine taxi/boarding chatter in the compact feed. */
const routine = (e: SimEvent) => e.kind === "status" && (e.status === "Boarding" || e.status === "In Flight")

export function EventFeed({ height = 520 }: { height?: number }) {
  const { events, state, airlineId } = useSim()
  const shown = React.useMemo(() => events.filter((e) => !routine(e)).slice(0, 50), [events])
  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto pr-1" style={{ maxHeight: height }}>
        {!state ? (
          <div className="grid gap-3 py-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : shown.length === 0 ? (
          <EmptyState icon={ListIcon} title="No events yet. Start the simulation to see departures, delays and cancellations." />
        ) : (
          <ul className="divide-y">
            <AnimatePresence initial={false}>
              {shown.map((e) => (
                <EventRow key={e.seq} e={e} animate />
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>
      <AllEvents airlineId={airlineId} />
    </div>
  )
}

function AllEvents({ airlineId }: { airlineId: number | null }) {
  const [rows, setRows] = React.useState<SimEvent[] | null>(null)
  return (
    <Dialog onOpenChange={(o) => o && api<SimEvent[]>(`/sim/events${qs({ airline: airlineId, limit: 500 })}`).then(setRows).catch(() => setRows([]))}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="mt-2 w-full text-muted-foreground">
          View all events
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Event log</DialogTitle>
          <DialogDescription>Latest 500 events from MongoDB (flight_events). Money impact is an estimate.</DialogDescription>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto pr-1">
          {rows == null ? <Skeleton className="h-40 w-full" /> : <ul className="divide-y">{rows.map((e) => <EventRow key={e.seq} e={e} />)}</ul>}
        </div>
      </DialogContent>
    </Dialog>
  )
}
