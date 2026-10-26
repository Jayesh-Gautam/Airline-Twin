import type { Metadata } from "next"
import { GeistMono } from "geist/font/mono"
import { GeistSans } from "geist/font/sans"

import "./globals.css"
import { AppSidebar } from "@/components/app-sidebar"
import { ConnectionGate } from "@/components/connection-gate"
import { SimProvider } from "@/components/sim-provider"
import { ThemeProvider } from "@/components/theme-provider"
import { TopBar } from "@/components/top-bar"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

export const metadata: Metadata = {
  title: "Airline Twin — operations simulator",
  description: "Simulation and analytics project over six fictional airlines (PySpark + MongoDB). Not a real flight-control system.",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={cn("antialiased", GeistSans.variable, GeistMono.variable)}>
      <body className="min-h-svh">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false} disableTransitionOnChange>
          <TooltipProvider delayDuration={200}>
            <SimProvider>
              <SidebarProvider>
                <AppSidebar />
                <SidebarInset className="min-w-0">
                  <TopBar />
                  <main className="mx-auto w-full max-w-[1440px] flex-1 p-4 md:p-6">
                    <ConnectionGate>{children}</ConnectionGate>
                  </main>
                </SidebarInset>
              </SidebarProvider>
            </SimProvider>
            <Toaster position="bottom-right" />
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
