"use client"

import * as React from "react"
import { animate } from "motion"
import type { LucideIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { FlightStatus } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Small "est." marker for every estimated number. */
export function Est({ className }: { className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge
          variant="outline"
          tabIndex={0}
          className={cn("h-4 rounded px-1 font-mono text-[10px] font-normal text-muted-foreground", className)}
        >
          est.
        </Badge>
      </TooltipTrigger>
      <TooltipContent>Illustrative estimate — see config.py</TooltipContent>
    </Tooltip>
  )
}

/** Number that tweens to its new value in 300 ms (mono, tabular). */
export function AnimatedNumber({
  value,
  format,
  className,
}: {
  value: number
  format: (v: number) => string
  className?: string
}) {
  const ref = React.useRef<HTMLSpanElement>(null)
  const prev = React.useRef(value)
  React.useEffect(() => {
    const from = prev.current
    prev.current = value
    if (!ref.current) return
    if (from === value) {
      ref.current.textContent = format(value)
      return
    }
    const c = animate(from, value, {
      duration: 0.3,
      ease: "easeOut",
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = format(v)
      },
    })
    return () => c.stop()
  }, [value, format])
  return (
    <span ref={ref} className={cn("num", className)}>
      {format(value)}
    </span>
  )
}

const STATUS_STYLE: Record<string, { dot: string; text: string }> = {
  Scheduled: { dot: "bg-neutral-status", text: "text-muted-foreground" },
  Boarding: { dot: "bg-primary", text: "text-foreground" },
  Delayed: { dot: "bg-delayed", text: "text-delayed" },
  Departed: { dot: "bg-primary", text: "text-foreground" },
  "In Flight": { dot: "bg-profit", text: "text-foreground" },
  Landed: { dot: "bg-neutral-status", text: "text-muted-foreground" },
  Cancelled: { dot: "bg-loss", text: "text-loss" },
}

export function StatusBadge({ status, delayed }: { status: FlightStatus | string; delayed?: boolean }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.Scheduled
  const dot = delayed && status !== "Cancelled" && status !== "Landed" ? "bg-delayed" : s.dot
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium whitespace-nowrap", s.text)}>
      <span className={cn("size-1.5 shrink-0 rounded-full", dot)} aria-hidden />
      {status}
    </span>
  )
}

export function EmptyState({
  icon: Icon,
  title,
  action,
  onAction,
  className,
}: {
  icon: LucideIcon
  title: string
  action?: string
  onAction?: () => void
  className?: string
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 py-12 text-center", className)}>
      <div className="flex size-10 items-center justify-center rounded-full border bg-muted/40">
        <Icon className="size-4 text-muted-foreground" strokeWidth={1.5} />
      </div>
      <p className="max-w-xs text-sm text-muted-foreground">{title}</p>
      {action && onAction ? (
        <Button size="sm" onClick={onAction}>
          {action}
        </Button>
      ) : null}
    </div>
  )
}

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string
  description?: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </div>
  )
}

export function Label12({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("text-xs font-medium tracking-wide text-muted-foreground uppercase", className)}>{children}</span>
  )
}

export function Signed({ value, format, className }: { value: number; format: (v: number) => string; className?: string }) {
  return <span className={cn("num", value < 0 ? "text-loss" : value > 0 ? "text-profit" : "", className)}>{format(value)}</span>
}
