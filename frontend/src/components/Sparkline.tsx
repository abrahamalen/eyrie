/** A small single-series trend: area + line, the last point emphasised, one value per point on hover. */
export function Sparkline({
  points,
  height = 72,
  labels = false,
  format,
}: {
  points: { label: string; value: number }[]
  height?: number
  labels?: boolean
  format: (n: number) => string
}) {
  const w = 460
  const n = points.length
  if (n < 2) return null
  const max = Math.max(...points.map((p) => p.value), 0.0001) * 1.12
  const pad = labels ? 16 : 3
  const x = (i: number) => 4 + (i * (w - 8)) / (n - 1)
  const y = (v: number) => 4 + (height - pad - 6) * (1 - v / max)
  const base = height - pad + 2
  const line = points.map((p, i) => `${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const last = points[n - 1]
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} role="img"
      aria-label={`${points.map((p) => `${p.label} ${format(p.value)}`).join(', ')}`}>
      <line x1={4} x2={w - 4} y1={base} y2={base} className="stroke-border" />
      <polygon points={`4,${base} ${line} ${w - 4},${base}`} className="fill-brand/10" />
      <polyline points={line} fill="none" className="stroke-brand" strokeWidth={2} strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={p.label} cx={x(i)} cy={y(p.value)} r={i === n - 1 ? 4 : 10}
          className={i === n - 1 ? 'fill-brand stroke-card' : 'fill-transparent'} strokeWidth={i === n - 1 ? 2 : 0}>
          <title>{`${p.label}: ${format(p.value)}`}</title>
        </circle>
      ))}
      {labels && [0, Math.floor((n - 1) / 2), n - 1].map((i) => (
        <text key={i} x={x(i)} y={height - 2} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
          className="fill-muted-foreground font-mono text-[10px] uppercase">{i === n - 1 ? 'Today' : points[i].label}</text>
      ))}
      <title>{`Today: ${format(last.value)}`}</title>
    </svg>
  )
}
