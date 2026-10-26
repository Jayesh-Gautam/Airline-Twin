"use client"

import * as React from "react"
import { PauseIcon, PlayIcon, RotateCcwIcon, SkipForwardIcon } from "lucide-react"

import { ConditionsIndicator } from "@/components/conditions-indicator"
import { ScenarioSheet } from "@/components/scenario-sheet"
import { useSim } from "@/components/sim-provider"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { airlineColor, SPEED_LABELS } from "@/lib/airlines"
import { hhmm } from "@/lib/format"
import { cn } from "@/lib/utils"

function Dot({ color }: { color: string }) {
  return <span className="size-2 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
}

export function TopBar() {
  const { airlines, airlineId, setAirlineId, state, connected, start, pause, nextDay, advance, reset, setSpeed, busy } = useSim()

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:px-6">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mx-1 data-vertical:h-4 data-vertical:self-auto" />

      <Select value={airlineId == null ? "all" : String(airlineId)} onValueChange={(v) => setAirlineId(v === "all" ? null : Number(v))}>
        <SelectTrigger size="sm" className="w-[200px]" aria-label="Airline">
          <SelectValue placeholder="Airline" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">
            <Dot color="var(--muted-foreground)" /> All airlines
          </SelectItem>
          {airlines.map((a) => (
            <SelectItem key={a.id} value={String(a.id)}>
              <Dot color={airlineColor(a.id)} /> {a.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="mx-auto flex items-center gap-2 px-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <span
              tabIndex={0}
              className={cn("size-1.5 rounded-full", connected ? "bg-profit" : "bg-loss")}
              aria-label={connected ? "live connection" : "disconnected"}
            />
          </TooltipTrigger>
          <TooltipContent>{connected ? "Live stream connected" : "Backend not reachable"}</TooltipContent>
        </Tooltip>
        {state ? (
          <span className="num text-lg font-medium tracking-tight whitespace-nowrap" aria-live="off">
            Day {state.day_index} <span className="text-muted-foreground">·</span> {state.weekday} {hhmm(state.clock)}
          </span>
        ) : (
          <Skeleton className="h-6 w-40" />
        )}
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center rounded-lg border p-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon-sm"
                variant={state?.running ? "secondary" : "default"}
                className="rounded-md"
                disabled={!state || busy}
                onClick={() => (state?.running ? pause() : start())}
                aria-label={state?.running ? "Pause" : "Start"}
              >
                {state?.running ? <PauseIcon strokeWidth={1.5} /> : <PlayIcon strokeWidth={1.5} />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{state?.running ? "Pause" : state && state.day_index > 1 ? "Resume" : "Start"}</TooltipContent>
          </Tooltip>
          <ToggleGroup
            type="single"
            size="sm"
            value={state ? String(state.speed) : ""}
            onValueChange={(v) => v && setSpeed(Number(v))}
            className="hidden sm:flex"
            aria-label="Simulation speed (sim time per real second)"
          >
            {(state?.speeds ?? [60, 300, 900, 1800, 3600]).map((s) => (
              <ToggleGroupItem key={s} value={String(s)} className="num h-8 px-2 text-xs" aria-label={`${SPEED_LABELS[s]} per second`}>
                {SPEED_LABELS[s]}/s
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <DropdownMenu>
            <Tooltip>
              <TooltipTrigger asChild>
                <DropdownMenuTrigger asChild>
                  <Button size="icon-sm" variant="ghost" disabled={!state || busy} aria-label="Fast-forward">
                    <SkipForwardIcon strokeWidth={1.5} />
                  </Button>
                </DropdownMenuTrigger>
              </TooltipTrigger>
              <TooltipContent>Fast-forward</TooltipContent>
            </Tooltip>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuLabel className="text-xs text-muted-foreground">Fast-forward to midnight</DropdownMenuLabel>
              <DropdownMenuItem onClick={nextDay}>Next day</DropdownMenuItem>
              {[7, 30, 90].map((d) => (
                <DropdownMenuItem key={d} onClick={() => advance(d)}>
                  +{d} days <span className="num ml-auto text-xs text-muted-foreground">{d === 90 ? "~10 s" : d === 30 ? "~3 s" : ""}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <Dialog>
            <Tooltip>
              <TooltipTrigger asChild>
                <DialogTrigger asChild>
                  <Button size="icon-sm" variant="ghost" disabled={!state || busy} aria-label="Reset simulation">
                    <RotateCcwIcon strokeWidth={1.5} />
                  </Button>
                </DialogTrigger>
              </TooltipTrigger>
              <TooltipContent>Reset</TooltipContent>
            </Tooltip>
            <DialogContent className="sm:max-w-sm">
              <DialogHeader>
                <DialogTitle>Reset the simulation?</DialogTitle>
                <DialogDescription>
                  Clears the simulated flights, events and daily P&amp;L (the sim_* collections) and starts again at day 1
                  with the same seed. Historical data is not touched.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <Button variant="ghost">Cancel</Button>
                </DialogClose>
                <DialogClose asChild>
                  <Button variant="destructive" onClick={reset}>
                    Reset
                  </Button>
                </DialogClose>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
        <ConditionsIndicator />
        <ScenarioSheet />
      </div>
    </header>
  )
}
