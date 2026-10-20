import { lazy, Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowUpRight, Plus } from 'lucide-react'
import { api } from '@/api/client'
import type { ExternalSession, Session } from '@/api/types'
import { usePoll } from '@/usePoll'
import { fmtAgo, fmtNum, shortPath, toolTitle } from '@/format'
import { sessionTools, toolInfo, useMeta } from '@/tools'
import { CopyButton } from '@/components/CopyButton'
import { StartSessionDialog, type StartRequest } from '@/components/StartSessionDialog'
import { StopSessionDialog } from '@/components/StopSessionDialog'
import { StopExternalDialog } from '@/components/StopExternalDialog'
import { StopAllDialog } from '@/components/StopAllDialog'
import { ContextHint, IdleBadge, SnoozeSelect } from '@/components/IdleBits'
import { costLine } from '@/lib/stop'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { PageHeader } from '@/components/PageHeader'

// xterm is large and only needed once a terminal opens.
const SessionTerminal = lazy(() => import('@/components/SessionTerminal').then((m) => ({ default: m.SessionTerminal })))

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/
const TERM_APPS = { terminal: 'Terminal', iterm: 'iTerm2' } as const
type TermApp = keyof typeof TERM_APPS

/** `?ext=<pid>&tool=<tool>&id=<conversation>` from the widget; anything odd is ignored. */
function parseExtLink(params: URLSearchParams, toolIds: string[]) {
  const pid = params.get('ext') ?? ''
  if (!/^\d{1,9}$/.test(pid)) return null
  const tool = params.get('tool')
  const id = params.get('id')
  return {
    pid: Number(pid),
    tool: tool && toolIds.includes(tool) ? tool : null,
    id: id && (UUID.test(id) || NAME.test(id)) ? id : null,
  }
}

/** What to paste to pick a conversation up again, when Eyrie has no directory for it. */
function resumeHint(tool: string, id: string) {
  return tool === 'codex' ? `codex resume ${id}` : tool === 'gemini' ? `gemini --resume ${id}` : `claude --resume ${id}`
}

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

/** The session's name, or its short id (mono) when it has none. */
function SessionName({ name, source, exact = true, id }: { name: string; source: Session['name_source']; exact?: boolean; id: string | null }) {
  const named = source === 'user' || source === 'tool'
  return (
    <div className={named ? 'font-medium' : 'font-mono text-xs'} title={id ? `Conversation ${id}` : undefined}>
      {!exact && <span title="Best guess: the newest conversation in this directory">~</span>}
      {name}
      {source === 'tool' && (
        <span className="ml-1.5 rounded border px-1 align-[1px] font-mono text-[10px] text-muted-foreground uppercase" title="Named by the tool, not by you">
          auto
        </span>
      )}
    </div>
  )
}

type Said = { ok: boolean; text: string }

export function SessionsPage() {
  const { data, error, refresh } = usePoll(api.sessions.list, 4_000)
  const convs = usePoll(() => api.sessions.conversations(10), 30_000)
  const codex = usePoll(api.codex, 30_000)
  const { tools, features } = useMeta()
  const [start, setStart] = useState<StartRequest | null>(null)
  // ?open=<name> (from the home page or the widget) opens that session's terminal;
  // ?ext=<pid> picks out one of the sessions in your own terminals.
  const [params, setParams] = useSearchParams()
  const [open, setOpen] = useState<string | null>(params.get('open'))
  const ext = parseExtLink(params, tools.map((t) => t.id))
  const [stopping, setStopping] = useState<Session | null>(null)
  const [stoppingExt, setStoppingExt] = useState<ExternalSession | null>(null)
  const [stopAll, setStopAll] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  // ?filter=idle (from the widget's "idle sessions" line) shows only idle sessions.
  const filter = params.get('filter') === 'idle' ? 'idle' : 'all'
  const setFilter = (f: 'all' | 'idle') => {
    const next = new URLSearchParams(params)
    if (f === 'idle') next.set('filter', 'idle')
    else next.delete('filter')
    setParams(next, { replace: true })
  }
  const [said, setSaid] = useState<Record<string, Said>>({})
  const [termApp, setTermApp] = useState<TermApp>(() => {
    try {
      return localStorage.getItem('eyrie-term-app') === 'iterm' ? 'iterm' : 'terminal'
    } catch {
      return 'terminal'
    }
  })
  const dirs = data?.dirs ?? []
  const allowed = (cwd: string | null) => !!cwd && dirs.includes(cwd)
  const allSessions = data?.sessions ?? []
  const allExternal = data?.external ?? []
  const shown = (i: { idle: Session['idle'] }) => filter === 'all' || !!i.idle?.idle
  const sessions = allSessions.filter(shown)
  const external = allExternal.filter(shown)
  const idleCount = [...allSessions, ...allExternal].filter((x) => x.idle?.idle).length
  const suggestedCount = [...allSessions, ...allExternal].filter((x) => x.idle?.suggested).length
  const snoozed = (n: string) => {
    setNote(n)
    refresh()
  }
  const openSession = allSessions.find((s) => s.name === open)
  const extGone = !!data && !!ext && !allExternal.some((x) => x.pid === ext.pid)

  // Bring the linked row into view when the link or the list first arrives, not on every poll.
  const scrollTo = ext && data ? ext.pid : null
  useEffect(() => {
    if (scrollTo !== null) document.getElementById(`ext-${scrollTo}`)?.scrollIntoView({ block: 'center' })
  }, [scrollTo])

  const say = (key: string, value: Said) => setSaid((m) => ({ ...m, [key]: value }))
  const act = async (key: string, id: string, p: object) => {
    say(key, { ok: true, text: '…' })
    try {
      const r = await api.actions.run(id, p)
      say(key, { ok: r.ok, text: r.message })
    } catch (e) {
      say(key, { ok: false, text: e instanceof Error ? e.message : String(e) })
    }
    refresh()
  }
  const jump = (x: ExternalSession) => act(`ext-${x.pid}`, 'sessions.focus', { pid: x.pid, tty: x.tty })
  const openIn = (s: Session) => {
    try {
      localStorage.setItem('eyrie-term-app', termApp)
    } catch {
      // Only a convenience.
    }
    act(s.name, 'sessions.open_terminal', { name: s.name, app: termApp })
  }
  const canResume = (tool: string | null, id: string | null) =>
    !!tool && !!id && UUID.test(id) && !!toolInfo(tool)?.session_modes.includes('resume')
  const resume = (tool: string, id: string, cwd: string | null) =>
    setStart({ tool: tool as StartRequest['tool'], cwd: cwd ?? undefined, mode: 'resume', resumeId: id,
      label: `Resume ${id.slice(0, 8)}${cwd ? ` in ${shortPath(cwd)}` : ''}.` })
  const clearLink = () => {
    const next = new URLSearchParams(params)
    for (const k of ['ext', 'tool', 'id']) next.delete(k)
    setParams(next, { replace: true })
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Work"
        title="Sessions"
        description={<>Claude Code, Codex and Gemini CLI running in Eyrie's own tmux server, and the ones in your terminals. Named the way you named them.</>}
        actions={
          <>
        <Button onClick={() => setStart({ tool: sessionTools()[0]?.id ?? 'claude' })} disabled={!data || !!data.error || !sessionTools().length}>
          <Plus className="size-4" /> New session
        </Button>
          </>
        }
      />

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Filter sessions" className="inline-flex overflow-hidden rounded-lg border bg-card text-sm">
          {(['all', 'idle'] as const).map((f) => (
            <button key={f} type="button" aria-pressed={filter === f} onClick={() => setFilter(f)}
              className={`px-3 py-1 ${filter === f ? 'bg-muted font-medium' : 'text-muted-foreground hover:bg-accent'}`}>
              {f === 'all' ? `All · ${allSessions.length + allExternal.length}` : `Idle · ${idleCount}`}
            </button>
          ))}
        </div>
        {data && <span className="text-xs text-muted-foreground">Idle = no activity for {data.idle_hours} h. Idle sessions don't use tokens; they hold memory.</span>}
        {note && <span role="status" className="text-xs text-muted-foreground">{note}</span>}
        <Button variant="outline" size="sm" className="ml-auto" onClick={() => setStopAll(true)} disabled={!data || !suggestedCount}>
          Stop all idle…
        </Button>
      </div>
      {data?.error && <p className="text-sm text-destructive">{data.error}</p>}

      {extGone && ext && (
        <Card role="status" className="border-l-4 border-l-amber-500">
          <CardContent className="flex flex-col gap-2 text-sm">
            <p>
              <span className="font-medium">That {ext.tool ? toolTitle(ext.tool) : ''} session isn't running any more</span>{' '}
              <span className="text-muted-foreground">(pid {ext.pid})</span>
            </p>
            {ext.tool && ext.id ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground">Resume it from its project directory:</span>
                <code className="rounded-md border bg-muted px-2 py-0.5 font-mono text-xs">{resumeHint(ext.tool, ext.id)}</code>
                <CopyButton text={resumeHint(ext.tool, ext.id)} />
                {canResume(ext.tool, ext.id) && (
                  <Button size="sm" onClick={() => resume(ext.tool!, ext.id!, null)}>Resume in Eyrie</Button>
                )}
              </div>
            ) : (
              <p className="text-muted-foreground">Eyrie doesn't know which conversation it was. Start a new session.</p>
            )}
            <div>
              <Button variant="ghost" size="sm" onClick={clearLink}>Dismiss</Button>
            </div>
          </CardContent>
        </Card>
      )}

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
                    <TableCell className="min-w-[13rem] whitespace-normal">
                      <SessionName name={s.display_name} source={s.name_source} id={s.conversation_id} />
                      <div className="font-mono text-xs text-muted-foreground">
                        {s.display_name !== s.name ? `${s.name} · ` : ''}
                        {toolTitle(s.tool)}
                        {s.mode && s.mode !== 'new' ? ` · ${s.mode}` : ''}
                      </div>
                      {s.alive && costLine(s.resources, s.idle) && <div className="text-xs text-muted-foreground">{costLine(s.resources, s.idle)}</div>}
                      <ContextHint idle={s.idle} />
                    </TableCell>
                    <TableCell className="max-w-xs truncate font-mono text-xs" title={s.cwd ?? undefined}>
                      {s.cwd ? shortPath(s.cwd) : '—'}
                    </TableCell>
                    <TableCell className="text-sm">
                      <State s={s} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">{fmtAgo(s.created)}</TableCell>
                    <TableCell className="text-muted-foreground">{s.idle?.idle ? <IdleBadge idle={s.idle} /> : fmtAgo(s.last_output)}</TableCell>
                    <TableCell className="whitespace-nowrap text-right">
                      {s.alive ? (
                        <>
                          <Button variant="ghost" size="sm" onClick={() => setOpen(open === s.name ? null : s.name)}>
                            {open === s.name ? 'Hide' : 'Open'}
                          </Button>
                          {features.terminal_windows && (
                            <span className="inline-flex items-center">
                              <Button variant="ghost" size="sm" onClick={() => openIn(s)} title="A new terminal window attached to this session">
                                Open in
                              </Button>
                              <select
                                aria-label="Terminal app"
                                className="h-7 rounded-md border bg-transparent px-1 text-xs"
                                value={termApp}
                                onChange={(e) => setTermApp(e.target.value as TermApp)}
                              >
                                {Object.entries(TERM_APPS).map(([k, v]) => (
                                  <option key={k} value={k}>{v}</option>
                                ))}
                              </select>
                            </span>
                          )}
                          <CopyButton text={s.attach} label="Attach" />
                          <SnoozeSelect idle={s.idle} name={s.display_name} onDone={snoozed} />
                        </>
                      ) : (
                        <>
                          {canResume(s.tool, s.conversation_id) && (
                            <Button variant="outline" size="sm" disabled={!allowed(s.cwd)}
                              title={allowed(s.cwd) ? 'Start a new Eyrie session on this conversation' : 'Directory is gone or not allowed'}
                              onClick={() => resume(s.tool!, s.conversation_id!, s.cwd)}>
                              Resume
                            </Button>
                          )}
                          {s.resume_command && <CopyButton text={s.resume_command} label="Resume command" />}
                        </>
                      )}
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setStopping(s)}>
                        {s.alive ? 'Stop' : 'Close'}
                      </Button>
                      {said[s.name] && (
                        <div role="status" className={`mt-1 whitespace-normal text-xs ${said[s.name].ok ? 'text-muted-foreground' : 'text-destructive'}`}>
                          {said[s.name].text}
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {data && !sessions.length && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-6 text-center text-muted-foreground">
                      {filter === 'idle' ? 'No idle Eyrie sessions.' : 'No Eyrie sessions yet. Start one, or resume a conversation below.'}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {!!allExternal.length && (
        <Card>
          <CardHeader>
            <CardTitle>In your terminals</CardTitle>
            <CardDescription>
              Sessions you started yourself. Jump switches to their terminal where the terminal allows it; Stop sends SIGTERM to that one process, after you confirm.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session</TableHead>
                  <TableHead>Directory</TableHead>
                  <TableHead>Terminal</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Last activity</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {external.map((x) => {
                  const msg = said[`ext-${x.pid}`]
                  const where = `${x.terminal ?? 'an unknown terminal'} on ${x.tty}`
                  return (
                    <TableRow key={x.pid} id={`ext-${x.pid}`} data-state={ext?.pid === x.pid ? 'selected' : undefined}>
                      <TableCell className="min-w-[13rem] whitespace-normal">
                        <SessionName name={x.display_name} source={x.name_source} exact={x.name_exact} id={x.conversation_id} />
                        <div className="font-mono text-xs text-muted-foreground">
                          {toolTitle(x.tool)} · pid {x.pid}
                          {x.resume ? ` · resume ${x.resume.slice(0, 12)}` : ''}
                        </div>
                        {costLine(x.resources, x.idle) && <div className="text-xs text-muted-foreground">{costLine(x.resources, x.idle)}</div>}
                        <ContextHint idle={x.idle} />
                      </TableCell>
                      <TableCell className="max-w-xs truncate font-mono text-xs" title={x.cwd ?? undefined}>
                        {x.cwd ? shortPath(x.cwd) : '—'}
                      </TableCell>
                      <TableCell className="text-sm">
                        {x.terminal ?? 'Unknown'} <span className="font-mono text-xs text-muted-foreground">{x.tty}</span>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{fmtAgo(x.started)}</TableCell>
                      <TableCell
                        className="text-muted-foreground"
                        title={x.activity_exact ? undefined : 'Approximate: newest conversation in this directory'}
                      >
                        {x.idle?.idle ? <IdleBadge idle={x.idle} /> : x.last_activity ? `${x.activity_exact ? '' : '~'}${fmtAgo(x.last_activity)}` : '—'}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="ml-auto flex max-w-[11rem] flex-wrap items-center justify-end gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={x.focus === 'none'}
                          title={x.focus === 'tab' ? `Select its ${x.terminal} tab` : x.focus === 'pane' ? 'Select its tmux pane'
                            : x.focus === 'app' ? `Bring ${x.terminal} to the front (Eyrie can't pick the tab)` : undefined}
                          onClick={() => jump(x)}
                        >
                          Jump <ArrowUpRight className="size-3.5" />
                        </Button>
                        <SnoozeSelect idle={x.idle} name={x.display_name} onDone={snoozed} />
                        <Button variant="ghost" size="sm" className="text-destructive" disabled={!x.uid_ok || !x.process_started}
                          title={x.uid_ok ? 'Send SIGTERM to this one process, after you confirm' : 'Runs as another user'}
                          onClick={() => setStoppingExt(x)}>
                          Stop
                        </Button>
                        </div>
                        {x.focus === 'none' && !msg && (
                          <div className="mt-1 ml-auto max-w-[26ch] text-xs text-muted-foreground">
                            Running in {where}. Eyrie can't switch to it; switch to it yourself.
                          </div>
                        )}
                        {msg && (
                          <div role="status" className={`mt-1 max-w-[34ch] text-xs ${msg.ok ? 'text-muted-foreground' : 'text-destructive'}`}>
                            {msg.text}
                          </div>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
                {!external.length && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-6 text-center text-muted-foreground">No idle sessions in your terminals.</TableCell>
                  </TableRow>
                )}
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
                    {fmtAgo(c.last)} · {fmtNum(c.messages)} {c.messages === 1 ? 'response' : 'responses'}
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
      <StopExternalDialog
        session={stoppingExt}
        onClose={() => {
          setStoppingExt(null)
          refresh()
        }}
      />
      <StopAllDialog
        open={stopAll}
        sessions={allSessions}
        external={allExternal}
        threshold={data?.idle_hours ?? 24}
        onClose={() => {
          setStopAll(false)
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
