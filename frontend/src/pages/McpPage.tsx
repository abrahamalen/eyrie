import { useState } from 'react'
import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { shortPath, tildify } from '@/format'
import { AddMcpDialog } from '@/components/AddMcpDialog'
import { RemoveMcpDialog } from '@/components/RemoveMcpDialog'
import { Button } from '@/components/ui/button'
import type { McpServer } from '@/api/types'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'

export function McpPage() {
  const { data, error, refresh } = usePoll(api.mcp, 10_000)
  const [removing, setRemoving] = useState<McpServer | null>(null)
  const failure = (name: string) => data?.last_known_failures.find((f) => f.name === name)
  const pluginOnly = data?.last_known_failures.filter((f) => !data.configured.some((m) => m.name === f.name)) ?? []

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <h1 className="text-2xl font-semibold tracking-tight">MCP Servers</h1>
          <p className="text-sm text-muted-foreground">
            Claude Code and Codex servers. Changes go through each tool's own CLI.
          </p>
        </div>
        <AddMcpDialog onDone={refresh} />
      </div>

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}

      <Card>
        <CardContent className="overflow-x-auto">
          {!data && !error ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Server</TableHead>
                  <TableHead>Client</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Last known</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.configured.map((m) => {
                  const f = failure(m.name)
                  return (
                    <TableRow key={`${m.client}:${m.scope}:${m.project}:${m.name}`}>
                      <TableCell>
                        <div className="font-medium">{m.name}</div>
                        <div className="max-w-md truncate font-mono text-xs text-muted-foreground" title={m.target}>
                          <span className="mr-1.5 rounded bg-muted px-1">{m.type}</span>
                          {tildify(m.target)}
                        </div>
                      </TableCell>
                      <TableCell>{m.client === 'claude' ? 'Claude Code' : 'Codex'}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {m.scope}
                        {m.project && <div className="text-xs">{shortPath(m.project)}</div>}
                      </TableCell>
                      <TableCell>
                        {f ? (
                          <Badge variant="destructive">failed ({f.detail})</Badge>
                        ) : (
                          <span className="text-xs text-muted-foreground">no recent failure</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setRemoving(m)}>
                          Remove
                        </Button>
                      </TableCell>
                    </TableRow>
                  )
                })}
                {pluginOnly.map((f) => (
                  <TableRow key={`plugin:${f.name}`}>
                    <TableCell className="font-medium">{f.name}</TableCell>
                    <TableCell>Claude Code</TableCell>
                    <TableCell className="text-muted-foreground">from a plugin</TableCell>
                    <TableCell>
                      <Badge variant="destructive">failed ({f.detail})</Badge>
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">manage on Plugins</TableCell>
                  </TableRow>
                ))}
                {data && !data.configured.length && !pluginOnly.length && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                      No servers configured. Add one above.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <RemoveMcpDialog
        server={removing}
        onClose={() => {
          setRemoving(null)
          refresh()
        }}
      />

      <p className="text-xs text-muted-foreground">
        "Last known" comes from recent session transcripts, not a live check: checking would mean launching every
        stdio server. Servers hidden with privacy.hide_mcp in eyrie.toml aren't listed.
      </p>
    </div>
  )
}
