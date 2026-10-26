"use client"

import { Line, LineChart, ReferenceLine, YAxis } from "recharts"

import { AnimatedNumber, Est, Label12 } from "@/components/bits"
import { Card } from "@/components/ui/card"
import { ChartContainer, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

type Props = {
  label: string
  value: number | null
  format: (v: number) => string
  estimate?: boolean
  delta?: number | null
  deltaLabel?: string
  spark?: number[]
  live?: boolean
  tone?: "auto" | "plain"
  hero?: boolean
  footer?: React.ReactNode
  className?: string
}

const sparkConfig = { v: { label: "value", color: "var(--muted-foreground)" } } satisfies ChartConfig

export function KpiCard({ label, value, format, estimate, delta, deltaLabel = "vs yesterday", spark, live, tone = "plain", hero, footer, className }: Props) {
  const signed = tone === "auto" && value != null
  return (
    <Card className={cn("flex h-full flex-col justify-between gap-3 rounded-xl p-4 shadow-none", className)}>
      <div className="flex items-center gap-2">
        <Label12>{label}</Label12>
        {estimate ? <Est /> : null}
        {live ? (
          <span className="relative ml-auto flex size-2" aria-label="simulation running">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-profit opacity-50" />
            <span className="relative inline-flex size-2 rounded-full bg-profit" />
          </span>
        ) : null}
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          {value == null ? (
            <Skeleton className={cn("h-8 w-28", hero && "h-10 w-36")} />
          ) : (
            <AnimatedNumber
              value={value}
              format={format}
              className={cn(
                "block truncate font-semibold tracking-tight",
                hero ? "text-[34px] leading-10" : "text-[28px] leading-8",
                signed && (value < 0 ? "text-loss" : value > 0 ? "text-profit" : "")
              )}
            />
          )}
          <div className="mt-1 h-4 truncate text-xs text-muted-foreground">
            {delta != null && Number.isFinite(delta) ? (
              <span className="whitespace-nowrap">
                <span className={cn("num", delta >= 0 ? "text-profit" : "text-loss")}>
                  {delta >= 0 ? "▲" : "▼"} {Math.abs(delta * 100) >= 1000 ? ">999" : Math.abs(delta * 100).toFixed(1)}%
                </span>{" "}
                {deltaLabel}
              </span>
            ) : (
              footer ?? null
            )}
          </div>
        </div>
        {spark && spark.length > 1 ? (
          <ChartContainer config={sparkConfig} className="aspect-auto h-10 w-24 shrink-0" initialDimension={{ width: 96, height: 40 }}>
            <LineChart data={spark.map((v, i) => ({ i, v }))} margin={{ top: 4, bottom: 4, left: 0, right: 0 }}>
              <YAxis hide domain={["dataMin", "dataMax"]} />
              {Math.min(...spark) < 0 && Math.max(...spark) > 0 ? (
                <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="2 2" />
              ) : null}
              <Line
                dataKey="v"
                type="monotone"
                dot={false}
                strokeWidth={1.5}
                isAnimationActive={false}
                stroke={tone === "auto" && spark[spark.length - 1] < 0 ? "var(--loss)" : tone === "auto" ? "var(--profit)" : "var(--muted-foreground)"}
              />
            </LineChart>
          </ChartContainer>
        ) : null}
      </div>
    </Card>
  )
}
