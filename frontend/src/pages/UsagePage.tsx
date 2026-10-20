import { useState } from 'react'
import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { fmtCompact, fmtNum, fmtUsd, shortPath, toolTitle } from '@/format'
import { StatTile } from '@/components/StatTile'
import { BarList } from '@/components/BarList'
import { UsageChart, UsageLegend } from '@/components/UsageChart'
import { type Metric, seriesColor } from '@/usageSeries'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/PageHeader'

const RANGES = [7, 30, 90] as const

function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  render,
}: {
  label: string
  options: readonly T[]
  value: T
  onChange: (v: T) => void
  render: (v: T) => string
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-lg border bg-card">
      {options.map((o) => (
        <button
          key={o}
          type="button"
          aria-pressed={o === value}
          onClick={() => onChange(o)}
          className="px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted aria-pressed:bg-muted aria-pressed:font-medium aria-pressed:text-foreground"
        >
          {render(o)}
        </button>
      ))}
    </div>
  )
}

export function UsagePage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(30)
  const [metric, setMetric] = useState<Metric>('cost')
  const { data, error } = usePoll(() => api.usage(days), 30_000, days)
  const fmt = metric === 'cost' ? fmtUsd : fmtCompact
  const stale = data && data.range.days !== days

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Work"
        title="Usage"
        description={<>Cost and tokens over time for every tool, from their session transcripts.</>}
        actions={
          <>
        <Segmented label="Metric" options={['cost', 'tokens'] as const} value={metric} onChange={setMetric}
          render={(m) => (m === 'cost' ? 'Cost' : 'Tokens')} />
        <Segmented label="Range" options={RANGES} value={days} onChange={setDays} render={(d) => `${d} days`} />
          </>
        }
      />

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}
      {!data && !error && <Skeleton className="h-80" />}

      {data && (
        <div className={`flex flex-col gap-6 ${stale ? 'opacity-60' : ''}`}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile value={fmtUsd(data.totals.cost)} label={`Cost at list prices, last ${data.range.days} days`} />
            <StatTile value={fmtCompact(data.totals.tokens)} label="Tokens, including cache" />
            <StatTile value={fmtNum(data.totals.sessions)} label="Sessions" />
            <StatTile value={fmtNum(data.totals.messages)} label="API responses" />
          </div>

          {data.by_tool.length > 1 && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {data.by_tool.map((t) => (
                <StatTile key={t.tool} value={metric === 'cost' ? fmtUsd(t.cost) : fmtCompact(t.tokens)}
                  label={`${toolTitle(t.tool)} · ${fmtNum(t.sessions)} sessions`} />
              ))}
            </div>
          )}

          {data.pricing.unpriced_models.length > 0 && (
            <div role="status" className="rounded-lg border border-amber-500/60 bg-amber-500/10 px-4 py-3 text-sm">
              No price for {data.pricing.unpriced_models.join(', ')}, so it counts as $0. Add it under [pricing] in
              eyrie.toml.
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>{metric === 'cost' ? 'Daily cost' : 'Daily tokens'} by tool</CardTitle>
              <CardDescription>
                <UsageLegend tools={data.by_model.map((m) => m.tool)} />
              </CardDescription>
            </CardHeader>
            <CardContent>
              <UsageChart
                report={data}
                metric={metric}
                format={fmt}
                tickFormat={metric === 'cost' ? (n) => '$' + fmtCompact(n) : fmtCompact}
              />
            </CardContent>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>By model</CardTitle>
              </CardHeader>
              <CardContent className="overflow-x-auto">
                <table className="w-full whitespace-nowrap text-sm">
                  <thead className="eyebrow tracking-[0.06em]">
                    <tr>
                      <th className="py-1.5 text-left font-medium">Model</th>
                      <th className="py-1.5 pl-4 text-left font-medium">Tool</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Cost</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Input</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Output</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Cache read</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Cache write</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {data.by_model.map((m) => (
                      <tr key={`${m.tool}:${m.model}`} className="border-t">
                        <td className="py-1.5">
                          <span className="inline-flex items-center gap-2">
                            <span className="size-2.5 shrink-0 rounded-sm" style={{ background: seriesColor(m.tool) }} />
                            {m.model}
                          </span>
                        </td>
                        <td className="py-1.5 pl-4 text-muted-foreground">{toolTitle(m.tool)}</td>
                        <td className="py-1.5 pl-4 text-right">{m.priced ? fmtUsd(m.cost) : 'no price'}</td>
                        <td className="py-1.5 pl-4 text-right">{fmtCompact(m.input)}</td>
                        <td className="py-1.5 pl-4 text-right">{fmtCompact(m.output)}</td>
                        <td className="py-1.5 pl-4 text-right">{fmtCompact(m.cache_read)}</td>
                        <td className="py-1.5 pl-4 text-right">{fmtCompact(m.cache_write)}</td>
                      </tr>
                    ))}
                    {!data.by_model.length && (
                      <tr>
                        <td colSpan={7} className="py-3 text-muted-foreground">No usage in this range.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>By project</CardTitle>
                <CardDescription>Each session counts toward the directory it started in</CardDescription>
              </CardHeader>
              <CardContent>
                <BarList
                  rows={data.by_project.slice(0, 8).map((p) => ({ name: shortPath(p.project), value: p[metric] }))}
                  format={fmt}
                  emptyLabel="No usage in this range."
                />
              </CardContent>
            </Card>
          </div>

          <p className="text-xs text-muted-foreground">
            {data.note} Prices updated {data.pricing.updated}. Index: {fmtNum(data.index.messages)} responses from{' '}
            {fmtNum(data.index.files)} transcripts
            {data.index.oldest ? `, since ${new Date(data.index.oldest).toLocaleDateString('en-GB')}` : ''}. Kept in
            ~/.eyrie/usage.db, so history stays after the tools prune old transcripts.
          </p>
        </div>
      )}
    </div>
  )
}
