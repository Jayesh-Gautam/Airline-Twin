"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useTheme } from "next-themes"
import { BarChart3Icon, ChartColumnIcon, InfoIcon, MapIcon, MoonIcon, PlaneIcon, RadioTowerIcon, RouteIcon, SunIcon } from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"

const NAV = [
  { title: "Live Operations", url: "/", icon: RadioTowerIcon },
  { title: "Flight Map", url: "/map", icon: MapIcon },
  { title: "Daily P&L", url: "/pnl", icon: ChartColumnIcon },
  { title: "Routes & Fleet", url: "/routes", icon: RouteIcon },
  { title: "Historical Analytics", url: "/history", icon: BarChart3Icon },
]

export function AppSidebar(props: React.ComponentProps<typeof Sidebar>) {
  const path = usePathname()
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)
  React.useEffect(() => setMounted(true), [])
  const dark = mounted ? resolvedTheme !== "light" : true

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild className="hover:bg-transparent">
              <Link href="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <PlaneIcon className="size-4" strokeWidth={1.5} />
                </div>
                <div className="grid flex-1 text-left leading-tight">
                  <span className="truncate text-sm font-semibold">Airline Twin</span>
                  <span className="truncate text-xs text-muted-foreground">PySpark · MongoDB</span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Operations</SidebarGroupLabel>
          <SidebarMenu>
            {NAV.map((item) => {
              const active = item.url === "/" ? path === "/" : path.startsWith(item.url)
              return (
                <SidebarMenuItem key={item.url}>
                  <SidebarMenuButton asChild isActive={active} tooltip={item.title}>
                    <Link href={item.url}>
                      <item.icon strokeWidth={1.5} />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div className="flex items-start gap-2 rounded-lg border px-2.5 py-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
          <InfoIcon className="mt-0.5 size-3.5 shrink-0" strokeWidth={1.5} />
          <span>Simulation, not real flight data. Airlines are fictional; costs are illustrative estimates.</span>
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={() => setTheme(dark ? "light" : "dark")} tooltip="Toggle theme">
              {dark ? <SunIcon strokeWidth={1.5} /> : <MoonIcon strokeWidth={1.5} />}
              <span>{dark ? "Light mode" : "Dark mode"}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
