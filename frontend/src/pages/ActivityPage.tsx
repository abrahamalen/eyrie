import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { Card, CardContent } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/PageHeader'

export function ActivityPage() {
  const { data, error } = usePoll(() => api.audit(200), 10_000)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="You" title="Activity" description={<>Every change Eyrie has made, from ~/.eyrie/audit.jsonl. Secret values are masked.</>} />
      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}
      <Card>
        <CardContent className="overflow-x-auto">
          {!data && !error ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Command</TableHead>
                  <TableHead>Result</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.map((e, i) => (
                  <TableRow key={`${e.ts}-${i}`}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {new Date(e.ts).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{e.action}</TableCell>
                    <TableCell className="max-w-lg whitespace-normal break-all font-mono text-xs">{e.argv.join(' ')}</TableCell>
                    <TableCell title={e.message}>
                      {e.ok ? (
                        <Badge variant="secondary">ok</Badge>
                      ) : (
                        <Badge variant="destructive">failed (exit {e.exit_code})</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {data && !data.length && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-muted-foreground">
                      Nothing yet. Changes you make on the MCP and Plugins pages show up here.
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
