import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'

export function McpPage() {
  const { data, error } = usePoll(api.mcp, 10_000)

  const rows: { name: string; type: string; failed?: { detail: string } }[] = []
  if (data) {
    for (const m of data.configured) {
      const f = data.last_known_failures.find((x) => x.name === m.name)
      rows.push({ name: m.name, type: m.type, failed: f ? { detail: f.detail } : undefined })
    }
    for (const f of data.last_known_failures) {
      if (!data.configured.some((m) => m.name === f.name)) {
        rows.push({ name: f.name, type: 'plugin', failed: { detail: f.detail } })
      }
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">MCP Servers</h1>
        <p className="text-sm text-muted-foreground">Configured servers and last-known connection status</p>
      </div>

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Servers</CardTitle>
        </CardHeader>
        <CardContent>
          {!data && !error ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r) => (
                  <TableRow key={r.name}>
                    <TableCell className="font-medium">{r.name}</TableCell>
                    <TableCell className="text-muted-foreground">{r.type}</TableCell>
                    <TableCell>
                      {r.failed ? (
                        <Badge variant="destructive">failed ({r.failed.detail})</Badge>
                      ) : (
                        <Badge className="bg-emerald-600 text-white hover:bg-emerald-600">ok</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {!rows.length && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                      None found
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        "Last known" status is recovered from recent session transcripts — not a live ping.
      </p>
    </div>
  )
}
