"use client"

import * as React from "react"
import dynamic from "next/dynamic"
import { useTheme } from "next-themes"
import { toast } from "sonner"

import { PageHeader } from "@/components/bits"
import { FlightSheet } from "@/components/flight-sheet"
import { MAP_COLORS, PLANE_PATH, type MapData } from "@/components/map/map-data"
import { useSim } from "@/components/sim-provider"
import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { api, qs } from "@/lib/api"
import { airlineColor } from "@/lib/airlines"

const LeafletMap = dynamic(() => import("@/components/map/leaflet-map"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> })
const OfflineMap = dynamic(() => import("@/components/map/offline-map"), { ssr: false, loading: () => <Skeleton className="h-full w-full" /> })

function Plane({ color }: { color: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden className="rotate-45">
      <path d={PLANE_PATH} fill={color} />
    </svg>
  )
}

export default function FlightMapPage() {
  const { flights, airlineId, airlines, airline } = useSim()
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)
  React.useEffect(() => setMounted(true), [])
  const dark = mounted ? resolvedTheme !== "light" : true
  const [data, setData] = React.useState<MapData | null>(null)
  const [mode, setMode] = React.useState<"online" | "offline">("online")
  const [selected, setSelected] = React.useState<string | null>(null)

  React.useEffect(() => {
    setData(null)
    api<MapData>(`/airports${qs({ airline: airlineId })}`).then(setData).catch(() => setData({ airports: [], routes: [] }))
  }, [airlineId])

  const airborne = flights.filter((f) => f.position)
  const delayed = airborne.filter((f) => f.delay_minutes >= 15).length
  const c = dark ? MAP_COLORS.dark : MAP_COLORS.light
  const shownAirlines = airline ? [airline] : airlines

  return (
    <div className="grid gap-4">
      <PageHeader
        title="Flight Map"
        description={
          <>
            Simulated positions · <span className="num">{airborne.length}</span> aircraft airborne
            {delayed ? <> · <span className="num text-delayed">{delayed}</span> delayed</> : null}
          </>
        }
      >
        <ToggleGroup type="single" size="sm" variant="outline" value={mode} onValueChange={(v) => v && setMode(v as "online" | "offline")} aria-label="Basemap">
          <ToggleGroupItem value="online" className="px-3 text-xs">OpenStreetMap</ToggleGroupItem>
          <ToggleGroupItem value="offline" className="px-3 text-xs">Offline outline</ToggleGroupItem>
        </ToggleGroup>
      </PageHeader>

      <Card className="relative isolate h-[calc(100svh-12.5rem)] min-h-[480px] overflow-hidden rounded-xl p-0 shadow-none">
        {!data || !mounted ? (
          <Skeleton className="h-full w-full rounded-none" />
        ) : mode === "online" ? (
          <LeafletMap
            data={data}
            flights={flights}
            selected={selected}
            onSelect={setSelected}
            dark={dark}
            onTilesFailed={() => {
              setMode("offline")
              toast.info("Map tiles unavailable", { description: "Switched to the offline world outline." })
            }}
          />
        ) : (
          <OfflineMap data={data} flights={flights} selected={selected} onSelect={setSelected} dark={dark} />
        )}

        <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] w-56 rounded-xl border bg-popover/90 p-3 text-xs shadow-sm backdrop-blur">
          <p className="mb-2 font-medium">Simulated positions</p>
          <ul className="grid gap-1.5 text-muted-foreground">
            <li className="flex items-center gap-2"><Plane color={c.onTime} /> In flight, on time</li>
            <li className="flex items-center gap-2"><Plane color={c.delayed} /> Delayed 15 min or more</li>
            <li className="flex items-center gap-2"><Plane color={c.departing} /> Departed, taxiing</li>
          </ul>
          <div className="my-2 h-px bg-border" />
          <ul className="grid gap-1.5 text-muted-foreground">
            {shownAirlines.map((a) => (
              <li key={a.id} className="flex items-center gap-2">
                <span className="h-0.5 w-4 rounded" style={{ background: airlineColor(a.id) }} aria-hidden /> {a.name}
              </li>
            ))}
          </ul>
        </div>
      </Card>
      <FlightSheet flight={flights.find((f) => f.id === selected) ?? null} onClose={() => setSelected(null)} />
    </div>
  )
}
