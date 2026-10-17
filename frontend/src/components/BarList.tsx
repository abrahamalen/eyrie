import { fmtNum, shortPath } from '../format'

export function BarList({
  rows,
  emptyLabel,
  format = fmtNum,
}: {
  rows: { name: string; value: number }[]
  emptyLabel: string
  format?: (n: number) => string
}) {
  if (!rows.length) return <div className="text-sm italic text-muted-foreground">{emptyLabel}</div>
  const max = Math.max(...rows.map((r) => r.value), 1)
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r) => {
        const pct = Math.max(2, Math.round((r.value / max) * 100))
        return (
          <div className="grid grid-cols-[minmax(0,220px)_1fr_90px] items-center gap-3 text-sm" key={r.name}>
            <div className="truncate text-muted-foreground" title={r.name}>
              {shortPath(r.name)}
            </div>
            <div className="h-2.5 overflow-hidden rounded bg-muted">
              <div className="h-full rounded bg-primary" style={{ width: `${pct}%` }} />
            </div>
            <div className="text-right tabular-nums">{format(r.value)}</div>
          </div>
        )
      })}
    </div>
  )
}
