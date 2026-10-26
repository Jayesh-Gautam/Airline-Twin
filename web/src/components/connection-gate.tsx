"use client"

import { ServerOffIcon } from "lucide-react"

import { useSim } from "@/components/sim-provider"
import { Card } from "@/components/ui/card"

/** Shows a clear, actionable message when the API (or MongoDB behind it) is down. */
export function ConnectionGate({ children }: { children: React.ReactNode }) {
  const { error, airlines } = useSim()
  if (error && !airlines.length) {
    return (
      <Card className="mx-auto mt-16 max-w-lg items-center gap-3 rounded-xl p-8 text-center shadow-none">
        <div className="flex size-10 items-center justify-center rounded-full border bg-muted/40">
          <ServerOffIcon className="size-4 text-muted-foreground" strokeWidth={1.5} />
        </div>
        <h2 className="text-base font-semibold">{error.message}</h2>
        <p className="text-sm text-muted-foreground">{error.hint ?? "Start the backend and MongoDB, then this page reconnects automatically."}</p>
        <code className="num rounded-md border bg-muted/40 px-2 py-1 text-xs">.\start.ps1</code>
      </Card>
    )
  }
  return <>{children}</>
}
