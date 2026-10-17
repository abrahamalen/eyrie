import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { fmtNum, fmtUsd } from '@/format'
import { StatTile } from '@/components/StatTile'
import { BarList } from '@/components/BarList'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/PageHeader'

export function ClaudePage() {
  const { data, error } = usePoll(api.claude, 10_000)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Agents" title="Claude Code" description={<>Each project's last Claude Code session, from ~/.claude.json. Full history is on the Usage page.</>} />

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}

      {!data && !error && (
        <div className="grid grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile value={fmtUsd(data.totals.cost_usd)} label="Total cost (last-session snapshots)" />
            <StatTile value={fmtNum(data.totals.input_tokens)} label="Input tokens" />
            <StatTile value={fmtNum(data.totals.output_tokens)} label="Output tokens" />
            <StatTile value={data.projects.length} label="Active projects" />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Cost by project</CardTitle>
              <CardDescription>Top 10 by most recent session cost</CardDescription>
            </CardHeader>
            <CardContent>
              <BarList
                rows={data.projects.slice(0, 10).map((p) => ({ name: p.path, value: p.cost_usd }))}
                emptyLabel="No recent session cost data found."
              />
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground">
            Per-project figures are each project's most recent session snapshot, not a cumulative daily total.
          </p>
        </>
      )}
    </div>
  )
}
