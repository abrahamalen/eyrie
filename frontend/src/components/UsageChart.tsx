import { useLayoutEffect, useRef, useState } from 'react'
import type { UsageReport } from '@/api/types'
import { toolTitle } from '@/format'
import { type Metric, seriesColor, seriesOrder, toolOfModel } from '@/usageSeries'

export type { Metric } from '@/usageSeries'

const H = 240
const PAD = { top: 12, right: 8, bottom: 26, left: 52 }
const GAP = 2

function niceStep(raw: number) {
  if (raw <= 0) return 1
  const p = 10 ** Math.floor(Math.log10(raw))
  const n = raw / p
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p
}

function topRounded(x: number, y: number, w: number, h: number, r: number) {
  r = Math.min(r, w / 2, h)
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`
}

export function UsageChart({
  report,
  metric,
  format,
  tickFormat = format,
}: {
  report: UsageReport
  metric: Metric
  format: (n: number) => string
  tickFormat?: (n: number) => string
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(800)
  const [hover, setHover] = useState<number | null>(null)

  useLayoutEffect(() => {
    const el = wrap.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, e.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const series = seriesOrder(report.by_model.map((m) => m.tool))
  const toolOf = toolOfModel(report)
  const days = report.days.map((d) => {
    const vals: Record<string, number> = {}
    for (const [model, v] of Object.entries(d.models)) {
      const s = toolOf(model)
      vals[s] = (vals[s] ?? 0) + v[metric]
    }
    return { day: d.day, vals, total: Object.values(vals).reduce((a, b) => a + b, 0) }
  })
  const max = Math.max(0, ...days.map((d) => d.total))
  if (max === 0) {
    return <div className="py-16 text-center text-sm text-muted-foreground">No usage in this range.</div>
  }

  const step = niceStep(max / 4)
  const yMax = Math.ceil(max / step) * step
  const plotW = width - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const slot = plotW / days.length
  const barW = Math.max(2, Math.min(28, slot * 0.72))
  const y = (v: number) => PAD.top + plotH - (v / yMax) * plotH
  const labelEvery = Math.ceil(days.length / Math.max(2, Math.floor(plotW / 64)))
  const ticks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, i) => i * step)
  const fmtDay = (d: string) =>
    new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
  const hovered = hover === null ? null : days[hover]

  return (
    <div ref={wrap} className="relative" onMouseLeave={() => setHover(null)}>
      <svg width={width} height={H} role="img" aria-label={`Daily ${metric} by tool; the tables below break it down by model and project`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} className="stroke-border" strokeWidth={1} />
            <text
              x={PAD.left - 8}
              y={y(t) + 4}
              textAnchor="end"
              className="fill-muted-foreground text-[11px] tabular-nums"
            >
              {tickFormat(t)}
            </text>
          </g>
        ))}
        {days.map((d, i) => {
          const x = PAD.left + i * slot + (slot - barW) / 2
          let base = y(0)
          const segs = series.filter((s) => (d.vals[s] ?? 0) > 0)
          return (
            <g key={d.day} opacity={hover === null || hover === i ? 1 : 0.45}>
              {segs.map((s, k) => {
                const h = (d.vals[s] / yMax) * plotH
                const top = base - h
                const drawH = k === segs.length - 1 ? h : Math.max(0, h - GAP)
                const drawY = k === segs.length - 1 ? top : top + GAP
                base = top
                return k === segs.length - 1 ? (
                  <path key={s} d={topRounded(x, drawY, barW, drawH, 4)} fill={seriesColor(s)} />
                ) : (
                  <rect key={s} x={x} y={drawY} width={barW} height={drawH} fill={seriesColor(s)} />
                )
              })}
            </g>
          )
        })}
        {days.map((d, i) =>
          i % labelEvery === (days.length - 1) % labelEvery ? (
            <text
              key={d.day}
              x={PAD.left + i * slot + slot / 2}
              y={H - 8}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px]"
            >
              {fmtDay(d.day)}
            </text>
          ) : null,
        )}
        {days.map((d, i) => (
          <rect
            key={d.day}
            x={PAD.left + i * slot}
            y={PAD.top}
            width={slot}
            height={plotH}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
          />
        ))}
      </svg>
      {hovered && hover !== null && (
        <div
          className="pointer-events-none absolute top-2 z-10 min-w-44 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md"
          style={
            PAD.left + hover * slot > width / 2
              ? { right: width - (PAD.left + hover * slot) + 8 }
              : { left: PAD.left + (hover + 1) * slot + 8 }
          }
        >
          <div className="mb-1 flex justify-between gap-4 font-medium">
            <span>{fmtDay(hovered.day)}</span>
            <span className="tabular-nums">{format(hovered.total)}</span>
          </div>
          {[...series].reverse().map((s) =>
            hovered.vals[s] ? (
              <div key={s} className="flex items-center gap-2 text-muted-foreground">
                <span className="size-2 rounded-sm" style={{ background: seriesColor(s) }} />
                <span className="flex-1">{toolTitle(s)}</span>
                <span className="tabular-nums text-foreground">{format(hovered.vals[s])}</span>
              </div>
            ) : null,
          )}
          {!hovered.total && <div className="text-muted-foreground">No usage</div>}
        </div>
      )}
    </div>
  )
}

export function UsageLegend({ tools }: { tools: string[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {seriesOrder(tools).map((s) => (
        <span key={s} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: seriesColor(s) }} />
          {toolTitle(s)}
        </span>
      ))}
    </div>
  )
}
