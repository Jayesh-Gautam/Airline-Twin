"use client"

import * as React from "react"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import { CircleMarker, MapContainer, Marker, Polyline, TileLayer, Tooltip as LTooltip } from "react-leaflet"

import type { Flight } from "@/lib/api"
import { airlineColor } from "@/lib/airlines"
import { alignLon, MAP_COLORS, PLANE_PATH, planeColor, type MapData, type MapRoute } from "./map-data"

const iconCache = new Map<string, L.DivIcon>()

function planeIcon(heading: number, color: string, selected: boolean) {
  const h = Math.round(heading / 3) * 3
  const key = `${h}|${color}|${selected}`
  let icon = iconCache.get(key)
  if (!icon) {
    const glow = selected ? `filter: drop-shadow(0 0 6px ${color}) drop-shadow(0 0 2px ${color});` : ""
    icon = L.divIcon({
      className: "plane-icon",
      iconSize: [22, 22],
      iconAnchor: [11, 11],
      html: `<svg width="22" height="22" viewBox="0 0 24 24" style="transform: rotate(${h}deg); ${glow}"><path d="${PLANE_PATH}" fill="${color}" stroke="rgba(0,0,0,.45)" stroke-width=".6"/></svg>`,
    })
    iconCache.set(key, icon)
  }
  return icon
}

function labelIcon(iata: string) {
  return L.divIcon({ className: "airport-label", iconSize: [28, 12], iconAnchor: [-5, 6], html: `<span>${iata}</span>` })
}

export default function LeafletMap({
  data,
  flights,
  selected,
  onSelect,
  dark,
  onTilesFailed,
}: {
  data: MapData
  flights: Flight[]
  selected: string | null
  onSelect: (id: string) => void
  dark: boolean
  onTilesFailed: () => void
}) {
  const routes = React.useMemo(() => new Map<string, MapRoute>(data.routes.map((r) => [`${r.airline_id}:${r.route}`, r])), [data.routes])
  const labels = React.useMemo(() => new Map(data.airports.map((a) => [a.iata, labelIcon(a.iata)])), [data.airports])
  const failures = React.useRef({ errors: 0, loads: 0 })
  const airborne = flights.filter((f) => f.position)

  return (
    <MapContainer center={[38, -25]} zoom={2.6} minZoom={2} zoomSnap={0.25} worldCopyJump className="h-full w-full" attributionControl>
      <TileLayer
        key={dark ? "dark" : "light"}
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        className="map-tiles"
        maxZoom={19}
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        eventHandlers={{
          tileload: () => {
            failures.current.loads++
          },
          tileerror: () => {
            failures.current.errors++
            if (failures.current.errors >= 4 && failures.current.loads === 0) onTilesFailed()
          },
        }}
      />
      {data.routes.map((r) => (
        <Polyline
          key={`${r.airline_id}:${r.route}`}
          positions={r.arc}
          pathOptions={{ color: airlineColor(r.airline_id), weight: 1, opacity: 0.35, interactive: false }}
        />
      ))}
      {data.airports.map((a) => (
        <React.Fragment key={a.iata}>
          <CircleMarker center={[a.lat, a.lon]} radius={2.5} pathOptions={{ color: (dark ? MAP_COLORS.dark : MAP_COLORS.light).ring, fillColor: (dark ? MAP_COLORS.dark : MAP_COLORS.light).dot, fillOpacity: 0.9, weight: 1 }}>
            <LTooltip direction="top" offset={[0, -4]}>{a.name}</LTooltip>
          </CircleMarker>
          <Marker position={[a.lat, a.lon]} icon={labels.get(a.iata)!} interactive={false} keyboard={false} />
        </React.Fragment>
      ))}
      {airborne.map((f) => (
        <Marker
          key={f.id}
          position={[f.position!.lat, alignLon(f, routes)]}
          icon={planeIcon(f.position!.heading, planeColor(f, dark), f.id === selected)}
          zIndexOffset={f.id === selected ? 1000 : 0}
          title={`${f.flight_number} ${f.origin}-${f.destination}`}
          alt={`${f.flight_number} ${f.origin} to ${f.destination}`}
          eventHandlers={{ click: () => onSelect(f.id) }}
        />
      ))}
    </MapContainer>
  )
}
