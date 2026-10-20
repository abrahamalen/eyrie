import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, ArrowUpRight } from 'lucide-react'
import { api, StaleError } from '@/api/client'
import type { ExternalSession, Session, SessionsSnapshot, Summary } from '@/api/types'
import { usePoll } from '@/usePoll'
import { fmtAgo, fmtBytes, fmtCount, fmtIdle, fmtTokens, fmtUsd, shortPath, toolTitle } from '@/format'
import { SnoozeSelect } from '@/components/IdleBits'
import { StopAllDialog } from '@/components/StopAllDialog'
import { StopExternalDialog } from '@/components/StopExternalDialog'
import { StopSessionDialog } from '@/components/StopSessionDialog'
import { PageHeader } from '@/components/PageHeader'
import { Sparkline } from '@/components/Sparkline'
import { StartSessionDialog, type StartRequest } from '@/components/StartSessionDialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

const LANDING_PAGE = 'https://alenabraham.me/eyrie'

const DOT: Record<string, string> = {
  problem: 'bg-destructive',
  attention: 'bg-amber-500',
  ok: 'bg-emerald-600',
}

function Dot({ tone }: { tone: keyof typeof DOT | string }) {
  return <span className={`inline-block size-2 shrink-0 rounded-full ${DOT[tone] ?? DOT.ok}`} />
}

function CardLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link to={to} className="ml-auto inline-flex items-center gap-1 text-[13px] font-medium hover:text-brand">
      {children} <ArrowRight className="size-3.5" />
    </Link>
  )
}

const today = () =>
  new Date().toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })

function stateLine(s: Summary) {
  const n = s.attention.length
  return n ? `${n} thing${n === 1 ? '' : 's'} need${n === 1 ? 's' : ''} you` : 'Nothing needs you right now'
}

export function OverviewPage() {
  const { data, error, refresh } = usePoll(api.summary, 10_000)
  const navigate = useNavigate()
  const [start, setStart] = useState<StartRequest | null>(null)
  const [newTask, setNewTask] = useState('')
  const [taskNote, setTaskNote] = useState<string | null>(null)
  // The stop dialogs need the full session rows, so they're fetched when one opens.
  const [snap, setSnap] = useState<SessionsSnapshot | null>(null)
  const [stopEyrie, setStopEyrie] = useState<Session | null>(null)
  const [stopExt, setStopExt] = useState<ExternalSession | null>(null)
  const [stopAll, setStopAll] = useState(false)
  const [suggestNote, setSuggestNote] = useState<string | null>(null)
  const openStop = async (key: string | null) => {
    try {
      const fresh = await api.sessions.list()
      setSnap(fresh)
      if (key === null) return setStopAll(true)
      const m = fresh.sessions.find((x) => x.idle?.key === key)
      const x = fresh.external.find((e) => e.idle?.key === key)
      if (m) setStopEyrie(m)
      else if (x) setStopExt(x)
      else setSuggestNote("That session isn't running any more.")
    } catch (e) {
      setSuggestNote(`Couldn't load sessions: ${e instanceof Error ? e.message : String(e)}`)
    }
  }
  const closeStop = () => {
    setStopEyrie(null)
    setStopExt(null)
    setStopAll(false)
    refresh()
  }

  // Task edits re-read the file first, so they carry its current etag and never clobber an
  // edit made in Obsidian (the same rule as the Tasks page).
  const tick = async (id: string) => {
    try {
      const { etag } = await api.tasks.list()
      await api.tasks.update(etag, id, { done: true })
      setTaskNote(null)
    } catch (e) {
      setTaskNote(e instanceof StaleError ? 'Tasks.md just changed; showing the latest.' : `Couldn't update: ${String(e)}`)
    }
    refresh()
  }
  const addTask = async () => {
    const text = newTask.trim()
    if (!text) return
    try {
      const { etag } = await api.tasks.list()
      await api.tasks.add(etag, text)
      setNewTask('')
      setTaskNote(null)
    } catch (e) {
      setTaskNote(`Couldn't add: ${e instanceof Error ? e.message : String(e)}`)
    }
    refresh()
  }

  const spend = data?.spend
  const tasks = data?.tasks
  const change = spend?.change_vs_prev_7_pct

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow={`Overview · ${today()}`}
        title="Here’s what’s going on."
        description="Live from your tools. Refreshes every few seconds."
        actions={
          <a href={LANDING_PAGE} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[13px] font-medium hover:text-brand">
            What is Eyrie? <ArrowUpRight className="size-3.5" />
          </a>
        }
      />

      {error && <p className="text-sm text-destructive">Couldn't reach Eyrie's API: {error}</p>}
      {!data && !error && <Skeleton className="h-64" />}

      {data && (
        <>
          <Card>
            <CardHeader className="flex items-center">
              <CardTitle className={data.attention.length ? 'flex items-center gap-2 text-brand' : ''}>
                {data.attention.length > 0 && <span className="size-1.5 rounded-full bg-brand" />}
                Needs you{data.attention.length ? ` · ${data.attention.length}` : ''}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col">
              {data.attention.length ? (
                data.attention.map((a) => (
                  <div key={`${a.kind}:${a.title}`} className="flex items-center gap-3 border-b py-3 last:border-b-0">
                    <Dot tone={a.severity} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{a.title}</div>
                      <div className="truncate text-[13px] text-muted-foreground">{a.detail}</div>
                    </div>
                    <Button variant="outline" size="sm" render={<Link to={a.href} />}>
                      {a.kind === 'session_idle' || a.kind === 'session_exited_error' ? 'Open' : 'Fix'}
                    </Button>
                  </div>
                ))
              ) : (
                <div className="flex items-center gap-3 py-2">
                  <Dot tone="ok" />
                  <div>
                    <div className="font-medium">Nothing needs you right now.</div>
                    <div className="text-[13px] text-muted-foreground">Sessions, servers and tools all look fine.</div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {data.suggestions.count > 0 && (
            <Card>
              <CardHeader className="flex items-center">
                <CardTitle className="flex items-center gap-2 text-brand">
                  <span className="size-1.5 rounded-full bg-brand" />
                  Suggestions · {data.suggestions.count}
                </CardTitle>
                <Button variant="outline" size="sm" className="ml-auto" onClick={() => openStop(null)}>
                  Stop all idle…
                </Button>
              </CardHeader>
              <CardContent className="flex flex-col">
                {data.suggestions.items.map((s) => (
                  <div key={s.key} className="flex flex-wrap items-start gap-3 border-b py-3 sm:flex-nowrap">
                    <span className="mt-2"><Dot tone="attention" /></span>
                    <div className="min-w-0 flex-1 basis-[calc(100%-2rem)] sm:basis-0">
                      <div className="truncate font-medium">{s.display_name}</div>
                      <div className="truncate text-[13px] text-muted-foreground">
                        {toolTitle(s.tool)} · {s.project ? shortPath(s.project) : '—'} · idle {s.idle_exact ? '' : '~'}{fmtIdle(s.idle_minutes)}
                      </div>
                      <div className="text-[13px] text-muted-foreground">
                        {[s.rss_bytes ? fmtBytes(s.rss_bytes) : null,
                          s.child_processes ? `${s.child_processes} child process${s.child_processes === 1 ? '' : 'es'}` : null,
                          s.context_tokens ? `${fmtTokens(s.context_tokens)} of context` : null].filter(Boolean).join(' · ')}
                      </div>
                      {s.compact_command && s.context_tokens && (
                        <div className="mt-1.5 max-w-[62ch] border-l-2 border-brand pl-2 text-xs text-muted-foreground">
                          Idle sessions don't use tokens. Its prompt cache has expired, so your next message re-reads{' '}
                          {fmtTokens(s.context_tokens)} of context. Run <code className="rounded bg-muted px-1 font-mono">{s.compact_command}</code> first, or start fresh.
                        </div>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5 pl-5 sm:pl-0">
                      <Button variant="outline" size="sm" onClick={() => openStop(s.key)}>Stop…</Button>
                      <SnoozeSelect idle={{ idle: true, key: s.key, snoozed_until: null, dismissed: false }} name={s.display_name}
                        onDone={(n) => { setSuggestNote(n); refresh() }} />
                    </div>
                  </div>
                ))}
                <p className="pt-3 text-[13px] text-muted-foreground">
                  Idle = no activity for {data.suggestions.idle_hours} h (<Link to="/settings" className="underline">change</Link>). Idle sessions don't use tokens; they hold memory.
                </p>
                {suggestNote && <p role="status" className="pt-1 text-[13px] text-muted-foreground">{suggestNote}</p>}
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-2 divide-border overflow-hidden rounded-xl bg-card ring-1 ring-border sm:grid-cols-4 sm:divide-x">
            {[
              [String(data.sessions.filter((s) => s.alive).length), 'Live sessions'],
              [fmtUsd(spend?.today), 'Cost today'],
              data.tasks ? [String(data.tasks.open_count), 'Open tasks'] : [String(data.health.usage_index?.messages ?? 0), 'Responses indexed'],
              [stateLine(data).startsWith('Nothing') ? 'All fine' : String(data.attention.length), 'Need you'],
            ].map(([v, k]) => (
              <div key={k} className="px-5 py-4">
                <div className="font-mono text-[24px] leading-tight tracking-[-0.02em] tabular-nums">{v}</div>
                <div className="text-[13px] text-muted-foreground">{k}</div>
              </div>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="flex items-center">
                <CardTitle>Sessions</CardTitle>
                <CardLink to="/sessions">All sessions</CardLink>
              </CardHeader>
              <CardContent className="flex flex-col">
                {data.sessions.map((s) => {
                  const idle = data.attention.some((a) => a.kind === 'session_idle' && a.href === s.href)
                  const named = s.name_source === 'user' || s.name_source === 'tool'
                  return (
                  <div key={s.pid ?? s.name} className="flex items-center gap-3 border-b py-3">
                    <Dot tone={!s.alive ? (s.exit_status ? 'problem' : 'ok') : idle ? 'attention' : 'ok'} />
                    <div className="min-w-0 flex-1">
                      <div className={`truncate text-[13.5px] ${named ? 'font-medium' : 'font-mono'}`} title={s.conversation_id ?? undefined}>{s.display_name}</div>
                      <div className="truncate text-[13px] text-muted-foreground">
                        {toolTitle(s.tool)} · {s.project ? shortPath(s.project) : '—'} ·{' '}
                        {!s.managed && s.tty ? `${s.tty} · ` : ''}
                        {!s.alive ? `exited${s.exit_status ? ` (${s.exit_status})` : ''}` : idle ? `idle ${s.idle_minutes} min` : !s.managed && s.idle_minutes ? `active ${fmtIdle(s.idle_minutes)} ago` : 'running'}
                      </div>
                    </div>
                    <Button variant="outline" size="sm" render={<Link to={s.href} />}>
                      Open
                    </Button>
                  </div>
                  )
                })}
                {!data.sessions.length && (
                  <p className="border-b py-3 text-[13px] text-muted-foreground">No sessions running. Start one in a recent project:</p>
                )}
                {data.recent_projects.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 pt-3">
                    <span className="eyebrow mr-1 text-[10.5px]">Start in</span>
                    {data.recent_projects.map((p) => (
                      <button
                        key={p.path}
                        type="button"
                        title={`${shortPath(p.path)} · last used ${fmtAgo(p.last_used)}`}
                        onClick={() => setStart({ tool: p.tool, cwd: p.path })}
                        className="rounded-full border bg-background px-2.5 py-0.5 font-mono text-[12.5px] hover:border-brand hover:text-brand"
                      >
                        {shortPath(p.path).split('/').pop() || '~'}
                      </button>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex items-center">
                <CardTitle>Spend · last 7 days</CardTitle>
                <CardLink to="/usage">Usage</CardLink>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="font-mono text-[32px] leading-none tracking-[-0.03em]">{fmtUsd(spend?.today)}</span>
                  <span className="text-muted-foreground">today</span>
                  <span className="ml-auto text-[13px] text-muted-foreground">
                    {change === null || change === undefined
                      ? 'No earlier week to compare'
                      : `${change >= 0 ? '+' : '−'}${Math.abs(change).toFixed(0)}% vs previous 7 days`}
                  </span>
                </div>
                {spend && (
                  <Sparkline
                    labels
                    format={fmtUsd}
                    points={spend.last_7_days.map((d) => ({
                      label: new Date(d.day + 'T00:00:00').toLocaleDateString('en-GB', { weekday: 'short' }),
                      value: d.cost,
                    }))}
                  />
                )}
                <div className="text-[13px] text-muted-foreground">
                  Yesterday {fmtUsd(spend?.yesterday)}
                  {spend?.top_project_today && (
                    <>
                      {' '}· top project today <span className="font-mono">{shortPath(spend.top_project_today)}</span>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>

            {tasks && (
              <Card>
                <CardHeader className="flex items-center">
                  <CardTitle>Tasks</CardTitle>
                  <CardLink to="/tasks">All tasks</CardLink>
                </CardHeader>
                <CardContent className="flex flex-col">
                  {tasks.next.map((t) => (
                    <label key={t.id} className="flex cursor-pointer items-center gap-3 border-b py-2.5">
                      <Checkbox checked={false} onCheckedChange={() => tick(t.id)} />
                      <span className="min-w-0 flex-1 truncate">{t.text}</span>
                    </label>
                  ))}
                  {!tasks.next.length && <p className="border-b py-2.5 text-[13px] text-muted-foreground">No open tasks.</p>}
                  {tasks.open_count > tasks.next.length && (
                    <p className="border-b py-2 text-[13px] text-muted-foreground">
                      and {tasks.open_count - tasks.next.length} more
                    </p>
                  )}
                  <form
                    className="flex gap-2 pt-3"
                    onSubmit={(e) => {
                      e.preventDefault()
                      addTask()
                    }}
                  >
                    <Input id="home-new-task" aria-label="New task" placeholder="Add a task" value={newTask} onChange={(e) => setNewTask(e.target.value)} />
                    <Button type="submit" variant="outline" disabled={!newTask.trim()}>
                      Add
                    </Button>
                  </form>
                  {taskNote && <p className="pt-2 text-[13px] text-muted-foreground">{taskNote}</p>}
                </CardContent>
              </Card>
            )}

            <Card>
              <CardHeader className="flex items-center">
                <CardTitle>Your setup</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="flex flex-wrap gap-x-5 gap-y-2 text-[13.5px]">
                  {(['tmux', 'claude', 'codex', 'gemini'] as const).map((tool) => {
                    const h = data.health[tool]
                    // Not enabled here (null), or neither installed nor used: not part of your setup.
                    if (!h || (!h.found && !h.used)) return null
                    return (
                      <span key={tool} className="inline-flex items-center gap-2" title={h.path ?? undefined}>
                        <Dot tone={h.found ? 'ok' : 'problem'} />
                        {tool} <span className="font-mono text-muted-foreground">{h.found ? (h.version ?? 'found') : 'not installed'}</span>
                      </span>
                    )
                  })}
                </div>
                {data.health.usage_index && (
                  <div className="border-t pt-3 text-[13px] text-muted-foreground">
                    Usage index: {fmtCount(data.health.usage_index.messages, 'response')} from{' '}
                    {fmtCount(data.health.usage_index.files, 'transcript')}
                    {data.health.usage_index.oldest &&
                      `, since ${new Date(data.health.usage_index.oldest).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      <StopSessionDialog session={stopEyrie} onClose={closeStop} />
      <StopExternalDialog session={stopExt} onClose={closeStop} />
      <StopAllDialog open={stopAll} sessions={snap?.sessions ?? []} external={snap?.external ?? []}
        threshold={snap?.idle_hours ?? 24} onClose={closeStop} />
      <StartSessionDialog
        request={start}
        dirs={data?.recent_projects.map((p) => p.path) ?? []}
        onClose={() => setStart(null)}
        onStarted={(name) => navigate(`/sessions?open=${name}`)}
      />
    </div>
  )
}
