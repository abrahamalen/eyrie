import { useState } from 'react'
import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { fmtCompact, fmtNum, fmtUsd, shortPath } from '@/format'
import { StatTile } from '@/components/StatTile'
import { BarList } from '@/components/BarList'
import { UsageChart, UsageLegend } from '@/components/UsageChart'
import { type Metric, seriesColor, seriesOf } from '@/usageSeries'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

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
      <div className="flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <h1 className="text-2xl font-semibold tracking-tight">Usage</h1>
          <p className="text-sm text-muted-foreground">
            Claude Code cost and tokens over time, from session transcripts.
          </p>
        </div>
        <Segmented label="Metric" options={['cost', 'tokens'] as const} value={metric} onChange={setMetric}
          render={(m) => (m === 'cost' ? 'Cost' : 'Tokens')} />
        <Segmented label="Range" options={RANGES} value={days} onChange={setDays} render={(d) => `${d} days`} />
      </div>

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}
      {!data && !error && <Skeleton className="h-80" />}

      {data && (
        <div className={`flex flex-col gap-6 ${stale ? 'opacity-60' : ''}`}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile value={fmtUsd(data.totals.cost)} label={`Claude cost, last ${data.range.days} days`} />
            <StatTile value={fmtCompact(data.totals.tokens)} label="Tokens, including cache" />
            <StatTile value={fmtNum(data.totals.sessions)} label="Sessions" />
            <StatTile value={fmtNum(data.totals.messages)} label="API responses" />
          </div>

          {data.pricing.unpriced_models.length > 0 && (
            <div role="status" className="rounded-lg border border-amber-500/60 bg-amber-500/10 px-4 py-3 text-sm">
              No price for {data.pricing.unpriced_models.join(', ')}, so it counts as $0. Add it under [pricing] in
              eyrie.toml.
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle>{metric === 'cost' ? 'Daily cost' : 'Daily tokens'} by model</CardTitle>
              <CardDescription>
                <UsageLegend models={data.by_model.map((m) => m.model)} />
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
                  <thead className="text-xs text-muted-foreground">
                    <tr>
                      <th className="py-1.5 text-left font-medium">Model</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Cost</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Input</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Output</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Cache read</th>
                      <th className="py-1.5 pl-4 text-right font-medium">Cache write</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {data.by_model.map((m) => (
                      <tr key={m.model} className="border-t">
                        <td className="py-1.5">
                          <span className="inline-flex items-center gap-2">
                            <span className="size-2.5 shrink-0 rounded-sm" style={{ background: seriesColor(seriesOf(m.model)) }} />
                            {m.model}
                          </span>
                        </td>
                        <td className="py-1.5 pl-4 text-right">{m.priced ? fmtUsd(m.cost) : 'no price'}</td>
                        <td className="py-1.5 pl-4 text-right">{fmtCompact(m.input)}</td>
                        <td className="py-1.5 pl-4 text-right">{fmtCompact(m.output)}</td>
                        <td className="py-1.5 pl-4 text-right">{fmtCompact(m.cache_read)}</td>
                        <td className="py-1.5 pl-4 text-right">{fmtCompact(m.cache_write)}</td>
                      </tr>
                    ))}
                    {!data.by_model.length && (
                      <tr>
                        <td colSpan={6} className="py-3 text-muted-foreground">No usage in this range.</td>
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

          <Card>
            <CardHeader>
              <CardTitle>Codex</CardTitle>
              <CardDescription>
                Codex keeps one lifetime token total per thread, so it can't be split by day. These are threads active
                in the last {data.range.days} days.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {data.codex.available ? (
                <div className="flex flex-col gap-4">
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    <StatTile value={fmtNum(data.codex.threads)} label="Active threads" />
                    <StatTile value={fmtCompact(data.codex.tokens)} label="Lifetime tokens in those threads" />
                  </div>
                  <BarList
                    rows={data.codex.by_model.map((m) => ({ name: m.model, value: m.tokens }))}
                    format={fmtCompact}
                    emptyLabel="No Codex threads in this range."
                  />
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {data.codex.error ? `Couldn't read Codex: ${data.codex.error}` : 'Codex state not found.'}
                </p>
              )}
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground">
            {data.note} Prices updated {data.pricing.updated}. Index: {fmtNum(data.index.messages)} responses from{' '}
            {fmtNum(data.index.files)} transcripts
            {data.index.oldest ? `, since ${new Date(data.index.oldest).toLocaleDateString('en-GB')}` : ''}. Kept in
            ~/.eyrie/usage.db, so history stays after Claude Code prunes old transcripts.
          </p>
        </div>
      )}
    </div>
  )
}
