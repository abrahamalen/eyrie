import { lazy, Suspense, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plus } from 'lucide-react'
import { api } from '@/api/client'
import type { Session } from '@/api/types'
import { usePoll } from '@/usePoll'
import { fmtAgo, fmtNum, shortPath } from '@/format'
import { CopyButton } from '@/components/CopyButton'
import { StartSessionDialog, type StartRequest } from '@/components/StartSessionDialog'
import { StopSessionDialog } from '@/components/StopSessionDialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { PageHeader } from '@/components/PageHeader'

// xterm is large and only needed once a terminal opens.
const SessionTerminal = lazy(() => import('@/components/SessionTerminal').then((m) => ({ default: m.SessionTerminal })))

function State({ s }: { s: Session }) {
  if (!s.alive) {
    return (
      <span className="inline-flex items-center gap-1.5 text-muted-foreground">
        <span className="size-2 rounded-full bg-muted-foreground/50" />
        exited{s.exit_status !== null ? ` (${s.exit_status})` : ''}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-2 rounded-full bg-emerald-500" />
      running{s.attached ? ` · ${s.attached} attached` : ''}
    </span>
  )
}

export function SessionsPage() {
  const { data, error, refresh } = usePoll(api.sessions.list, 4_000)
  const convs = usePoll(() => api.sessions.conversations(10), 30_000)
  const codex = usePoll(api.codex, 30_000)
  const [start, setStart] = useState<StartRequest | null>(null)
  // ?open=<name> (from the home page or the widget) opens that session's terminal.
  const [params] = useSearchParams()
  const [open, setOpen] = useState<string | null>(params.get('open'))
  const [stopping, setStopping] = useState<Session | null>(null)
  const dirs = data?.dirs ?? []
  const allowed = (cwd: string | null) => !!cwd && dirs.includes(cwd)
  const sessions = data?.sessions ?? []
  const external = data?.external ?? []
  const openSession = sessions.find((s) => s.name === open)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Work"
        title="Sessions"
        description={<>Claude Code and Codex running in Eyrie's own tmux server. They keep running if Eyrie restarts.</>}
        actions={
          <>
        <Button onClick={() => setStart({ tool: 'claude' })} disabled={!data || !!data.error}>
          <Plus className="size-4" /> New session
        </Button>
          </>
        }
      />

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}
      {data?.error && <p className="text-sm text-destructive">{data.error}</p>}

      <Card>
        <CardContent className="overflow-x-auto">
          {!data && !error ? (
            <Skeleton className="h-24" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session</TableHead>
                  <TableHead>Directory</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Last output</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.map((s) => (
                  <TableRow key={s.name} data-state={open === s.name ? 'selected' : undefined}>
                    <TableCell>
                      <div className="font-mono text-xs">{s.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {s.tool === 'codex' ? 'Codex' : 'Claude Code'}
                        {s.mode && s.mode !== 'new' ? ` · ${s.mode}` : ''}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-xs truncate font-mono text-xs" title={s.cwd ?? undefined}>
                      {s.cwd ? shortPath(s.cwd) : '—'}
                    </TableCell>
                    <TableCell className="text-sm">
                      <State s={s} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">{fmtAgo(s.created)}</TableCell>
                    <TableCell className="text-muted-foreground">{fmtAgo(s.last_output)}</TableCell>
                    <TableCell className="whitespace-nowrap text-right">
                      <Button variant="ghost" size="sm" onClick={() => setOpen(open === s.name ? null : s.name)}>
                        {open === s.name ? 'Hide' : 'Open'}
                      </Button>
                      <CopyButton text={s.attach} label="Attach" />
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setStopping(s)}>
                        {s.alive ? 'Stop' : 'Close'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {data && !sessions.length && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-6 text-center text-muted-foreground">
                      No Eyrie sessions yet. Start one, or resume a conversation below.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {!!external.length && (
        <Card>
          <CardHeader>
            <CardTitle>In your terminals</CardTitle>
            <CardDescription>
              Claude Code and Codex you started yourself. Eyrie can see them but not attach; switch to that terminal.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tool</TableHead>
                  <TableHead>Directory</TableHead>
                  <TableHead>Terminal</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Last activity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {external.map((x) => (
                  <TableRow key={x.pid}>
                    <TableCell>
                      <div>{x.tool === 'codex' ? 'Codex' : 'Claude Code'}</div>
                      {x.resume && <div className="font-mono text-xs text-muted-foreground">resume {x.resume.slice(0, 12)}</div>}
                    </TableCell>
                    <TableCell className="max-w-xs truncate font-mono text-xs" title={x.cwd ?? undefined}>
                      {x.cwd ? shortPath(x.cwd) : '—'}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{x.tty} · pid {x.pid}</TableCell>
                    <TableCell className="text-muted-foreground">{fmtAgo(x.started)}</TableCell>
                    <TableCell
                      className="text-muted-foreground"
                      title={x.activity_exact ? undefined : 'Approximate: newest conversation in this directory'}
                    >
                      {x.last_activity ? `${x.activity_exact ? '' : '~'}${fmtAgo(x.last_activity)}` : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {openSession && (
        <Suspense fallback={<Skeleton className="h-[28rem]" />}>
          <SessionTerminal key={openSession.name} session={openSession} />
        </Suspense>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recent Claude Code conversations</CardTitle>
            <CardDescription>Resume one in a new tmux session</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col">
            {convs.data?.map((c) => (
              <div key={c.id} className="flex items-center gap-3 border-b py-2 text-sm last:border-b-0">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-xs">{c.project ? shortPath(c.project) : '(unknown directory)'}</div>
                  <div className="text-xs text-muted-foreground">
                    {fmtAgo(c.last)} · {fmtNum(c.messages)} responses
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!allowed(c.project)}
                  title={allowed(c.project) ? undefined : 'Directory is gone or not allowed'}
                  onClick={() => setStart({ tool: 'claude', cwd: c.project ?? undefined, mode: 'resume', resumeId: c.id,
                    label: `Resume conversation ${c.id.slice(0, 8)} in ${shortPath(c.project ?? '')}.` })}
                >
                  Resume
                </Button>
              </div>
            ))}
            {convs.data && !convs.data.length && <p className="text-sm text-muted-foreground">No conversations found.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Codex threads</CardTitle>
            <CardDescription>Resume one in a new tmux session</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col">
            {codex.data?.threads.slice(0, 10).map((t) => (
              <div key={t.id} className="flex items-center gap-3 border-b py-2 text-sm last:border-b-0">
                <div className="min-w-0 flex-1">
                  <div className="truncate">{t.title || '(untitled)'}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    <span className="font-mono">{shortPath(t.cwd)}</span> · {fmtAgo(new Date(t.updated_at * 1000).toISOString())}
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!allowed(t.cwd)}
                  title={allowed(t.cwd) ? undefined : 'Directory is gone or not allowed'}
                  onClick={() => setStart({ tool: 'codex', cwd: t.cwd, mode: 'resume', resumeId: t.id,
                    label: `Resume “${t.title || t.id}” in ${shortPath(t.cwd)}.` })}
                >
                  Resume
                </Button>
              </div>
            ))}
            {codex.data && !codex.data.threads.length && <p className="text-sm text-muted-foreground">No Codex threads found.</p>}
          </CardContent>
        </Card>
      </div>

      <StopSessionDialog
        session={stopping}
        onClose={(stopped) => {
          if (stopped && open === stopping?.name) setOpen(null)
          setStopping(null)
          refresh()
        }}
      />
      <StartSessionDialog
        request={start}
        dirs={dirs}
        onClose={() => setStart(null)}
        onStarted={(name) => {
          setOpen(name)
          refresh()
        }}
      />
    </div>
  )
}
