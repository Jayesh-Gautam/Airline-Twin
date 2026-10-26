"use client"

import * as React from "react"
import { ComposableMap, Geographies, Geography, Line, Marker, ZoomableGroup } from "react-simple-maps"
import { feature } from "topojson-client"
import type { Topology } from "topojson-specification"
import world from "world-atlas/countries-110m.json"

import type { Flight } from "@/lib/api"
import { airlineColor } from "@/lib/airlines"
import { alignLon, MAP_COLORS, PLANE_PATH, planeColor, type MapData, type MapRoute } from "./map-data"

const topo = world as unknown as Topology
const countries = feature(topo, topo.objects.countries) as unknown as GeoJSON.FeatureCollection

/** Offline fallback: a world outline bundled with the app (world-atlas TopoJSON), no tiles needed. */
export default function OfflineMap({
  data,
  flights,
  selected,
  onSelect,
  dark,
}: {
  data: MapData
  flights: Flight[]
  selected: string | null
  onSelect: (id: string) => void
  dark: boolean
}) {
  const mc = dark ? MAP_COLORS.dark : MAP_COLORS.light
  const routes = React.useMemo(() => new Map<string, MapRoute>(data.routes.map((r) => [`${r.airline_id}:${r.route}`, r])), [data.routes])
  return (
    <ComposableMap projection="geoEqualEarth" projectionConfig={{ scale: 230, center: [-20, 25] }} className="h-full w-full" width={1000} height={560}>
      <ZoomableGroup minZoom={1} maxZoom={6}>
        <Geographies geography={countries}>
          {({ geographies }) =>
            geographies.map((g) => (
              <Geography
                key={g.rsmKey}
                geography={g}
                style={{ fill: mc.land, stroke: mc.border, strokeWidth: 0.5, outline: "none" }}
              />
            ))
          }
        </Geographies>
        {data.routes.map((r) => (
          <Line
            key={`${r.airline_id}:${r.route}`}
            coordinates={r.arc.map(([la, lo]) => [lo, la] as [number, number])}
            stroke={airlineColor(r.airline_id)}
            strokeOpacity={0.35}
            strokeWidth={0.8}
            fill="none"
          />
        ))}
        {data.airports.map((a) => (
          <Marker key={a.iata} coordinates={[a.lon, a.lat]}>
            <circle r={1.8} fill={mc.dot} />
            <text x={4} y={3} fontSize={7} fill={mc.label} className="num">{a.iata}</text>
          </Marker>
        ))}
        {flights
          .filter((f) => f.position)
          .map((f) => {
            const c = planeColor(f, dark)
            return (
              <Marker key={f.id} coordinates={[alignLon(f, routes), f.position!.lat]} onClick={() => onSelect(f.id)} style={{ cursor: "pointer" }}>
                <g transform={`rotate(${f.position!.heading}) translate(-8,-8) scale(0.66)`} style={f.id === selected ? { filter: `drop-shadow(0 0 4px ${c})` } : undefined}>
                  <path d={PLANE_PATH} fill={c} stroke="rgba(0,0,0,.45)" strokeWidth={0.6} />
                </g>
                <title>{`${f.flight_number} ${f.origin}-${f.destination}`}</title>
              </Marker>
            )
          })}
      </ZoomableGroup>
    </ComposableMap>
  )
}
