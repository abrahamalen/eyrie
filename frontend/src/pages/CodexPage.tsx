import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { fmtNum } from '@/format'
import { StatTile } from '@/components/StatTile'
import { BarList } from '@/components/BarList'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/PageHeader'

export function CodexPage() {
  const { data, error } = usePoll(api.codex, 10_000)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Agents" title="Codex" description={<>Recent Codex threads, from ~/.codex/state_5.sqlite.</>} />

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}

      {!data && !error && (
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <StatTile value={fmtNum(data.threads.length)} label="Recent threads (top 200)" />
            <StatTile value={Object.keys(data.by_cwd).length} label="Distinct repos used" />
            <StatTile value={Object.keys(data.by_model).length} label="Models used" />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Tokens by repo</CardTitle>
              <CardDescription>Top 10 by token usage</CardDescription>
            </CardHeader>
            <CardContent>
              <BarList
                rows={Object.entries(data.by_cwd)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 10)
                  .map(([cwd, tokens]) => ({ name: cwd, value: tokens }))}
                emptyLabel="No Codex thread data found."
              />
            </CardContent>
          </Card>

          <p className="text-xs text-muted-foreground">
            "tokens_used" is Codex's own internal per-thread counter — treat as a relative signal, not a verified
            token/cost figure.
          </p>
        </>
      )}
    </div>
  )
}
