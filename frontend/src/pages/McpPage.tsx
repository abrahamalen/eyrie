import { useState } from 'react'
import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { shortPath, tildify, toolTitle } from '@/format'
import { AddMcpDialog } from '@/components/AddMcpDialog'
import { RemoveMcpDialog } from '@/components/RemoveMcpDialog'
import { Button } from '@/components/ui/button'
import type { McpServer } from '@/api/types'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/PageHeader'

export function McpPage() {
  const { data, error, refresh } = usePoll(api.mcp, 10_000)
  const [removing, setRemoving] = useState<McpServer | null>(null)
  const failure = (name: string) => data?.last_known_failures.find((f) => f.name === name)
  const pluginOnly = data?.last_known_failures.filter((f) => !data.configured.some((m) => m.name === f.name)) ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Tools"
        title="MCP servers"
        description={<>Claude Code and Codex servers. Changes go through each tool's own CLI.</>}
        actions={
          <>
        <AddMcpDialog onDone={refresh} />
          </>
        }
      />

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}

      <Card>
        <CardContent>
          {!data && !error ? (
            <Skeleton className="h-32" />
          ) : (
            <>
            {/* A phone is too narrow for the table's five columns: one stacked entry per server. */}
            <ul className="flex flex-col divide-y sm:hidden" aria-label="MCP servers">
              {data?.configured.map((m) => {
                const f = failure(m.name)
                return (
                  <li key={`${m.client}:${m.scope}:${m.project}:${m.name}`} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate font-medium">{m.name}</span>
                      <Button variant="ghost" size="sm" className="-mr-2 text-destructive" onClick={() => setRemoving(m)}>
                        Remove
                      </Button>
                    </div>
                    <div className="break-all font-mono text-xs text-muted-foreground">
                      <span className="mr-1.5 rounded bg-muted px-1">{m.type}</span>
                      {tildify(m.target)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {toolTitle(m.client)} · {m.scope}
                      {m.project && <> · {shortPath(m.project)}</>}
                    </div>
                    <div>
                      {f ? (
                        <Badge variant="destructive">failed ({f.detail})</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">no recent failure</span>
                      )}
                    </div>
                  </li>
                )
              })}
              {pluginOnly.map((f) => (
                <li key={`plugin:${f.name}`} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
                  <span className="font-medium">{f.name}</span>
                  <div className="text-xs text-muted-foreground">Claude Code · from a plugin · manage on Plugins</div>
                  <div>
                    <Badge variant="destructive">failed ({f.detail})</Badge>
                  </div>
                </li>
              ))}
              {data && !data.configured.length && !pluginOnly.length && (
                <li className="text-center text-sm text-muted-foreground">No servers configured. Add one above.</li>
              )}
            </ul>
            <Table className="max-sm:hidden">
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
                      <TableCell>{toolTitle(m.client)}</TableCell>
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
            </>
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
