import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'

export function NexusPage() {
  const { data, error } = usePoll(() => api.nexus(), 15_000)
  const agents = data?.agents ?? []

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Nexus Agents</h1>
        <p className="text-sm text-muted-foreground">Agent memory activity in the vault's Nexus/ folder</p>
      </div>

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Agents</CardTitle>
        </CardHeader>
        <CardContent>
          {!data && !error ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Agent</TableHead>
                  <TableHead>Memory files</TableHead>
                  <TableHead>Last used</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {agents.map((a) => (
                  <TableRow key={a.agent}>
                    <TableCell className="font-medium">{a.agent}</TableCell>
                    <TableCell>{a.file_count}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(a.last_used).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
                {!agents.length && (
                  <TableRow>
                    <TableCell colSpan={3} className="text-center text-muted-foreground">
                      No Nexus agent activity yet
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
