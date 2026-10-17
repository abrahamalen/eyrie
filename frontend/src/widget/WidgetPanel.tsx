import { useEffect, useState } from 'react'
import type { Summary } from '@/api/types'
import { fmtUsd, shortPath, setHome } from '@/format'
import { Sparkline } from '@/components/Sparkline'
import { bridge, type WidgetSettings } from './bridge'

const DOT: Record<string, string> = { problem: 'bg-destructive', attention: 'bg-amber-500', ok: 'bg-emerald-600' }
const Dot = ({ tone }: { tone: string }) => <span className={`inline-block size-2 shrink-0 rounded-full ${DOT[tone] ?? DOT.ok}`} />

function stateText(s: Summary) {
  const n = s.attention.length
  return n === 0 ? 'All fine' : n === 1 ? '1 needs you' : `${n} need you`
}

function newName() {
  const b = crypto.getRandomValues(new Uint8Array(3))
  return 'eyrie-' + Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
}

const btn = 'inline-flex items-center justify-center rounded-md border bg-card px-2.5 py-1 text-[12.5px] font-medium hover:bg-accent disabled:opacity-50'
const ghost = 'inline-flex items-center rounded-md px-2 py-1 text-[12.5px] font-medium hover:bg-accent'

type Pending = { path: string; tool: 'claude' | 'codex'; params: object; argv: string[] | null; error: string | null }

export function WidgetPanel() {
  const [s, setS] = useState<Summary | null>(null)
  const [down, setDown] = useState<string | null>(null)
  const [settings, setSettings] = useState<WidgetSettings | null>(null)
  const [picking, setPicking] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const [task, setTask] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    bridge.summary().then(setS).catch((e) => setDown(String(e)))
    bridge.settings().then((x) => {
      setHome(x.home)
      setSettings(x)
    })
    const subs = [
      bridge.onSummary((x) => {
        setS(x)
        setDown(null)
      }),
      bridge.onUnreachable((e) => setDown(e)),
    ]
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && bridge.hide()
    window.addEventListener('keydown', onKey)
    return () => {
      subs.forEach((p) => p.then((un) => un()))
      window.removeEventListener('keydown', onKey)
    }
  }, [])

  const preview = async (path: string, tool: 'claude' | 'codex') => {
    const params = {
      tool,
      cwd: path,
      mode: 'new',
      name: newName(),
      ...(tool === 'claude' ? { conversation_id: crypto.randomUUID() } : {}),
    }
    setPending({ path, tool, params, argv: null, error: null })
    const r = await bridge.action('sessions.start', params, { dry_run: true })
    setPending((p) => p && { ...p, argv: r.body.argv ?? null, error: r.status === 200 ? null : String(r.body.detail ?? 'Not allowed') })
  }

  const start = async () => {
    if (!pending) return
    const r = await bridge.action('sessions.start', pending.params)
    if (r.status === 200 && r.body.ok) {
      const name = (pending.params as { name: string }).name
      setPending(null)
      setPicking(false)
      await bridge.refresh()
      bridge.open(`/sessions?open=${name}`)
    } else {
      setPending((p) => p && { ...p, error: r.body.message || String(r.body.detail ?? 'Failed') })
    }
  }

  const addTask = async () => {
    const text = task?.trim()
    if (!text) return
    try {
      await bridge.addTask(text)
      setTask(null)
      setNote(`Added “${text}”`)
      bridge.refresh()
    } catch (e) {
      setNote(String(e))
    }
  }

  if (down && !s) {
    return (
      <Shell state="problem" label="Not answering">
        <section className="flex flex-col gap-2 px-4 py-4 text-[13px]">
          <p className="font-medium">Eyrie isn’t answering.</p>
          <p className="text-muted-foreground">{down}</p>
          <div className="flex gap-2 pt-1">
            <button className={btn} onClick={() => bridge.startEyrie().then((m) => setNote(m)).catch((e) => setNote(String(e)))}>
              Start Eyrie
            </button>
            <button className={ghost} onClick={() => bridge.refresh().then(setS).catch((e) => setDown(String(e)))}>
              Try again
            </button>
          </div>
          {note && <p className="font-mono text-[11.5px] text-muted-foreground">{note}</p>}
          <p className="text-[12px] text-muted-foreground">Not installed yet? From the repo: <span className="font-mono">make install</span></p>
        </section>
      </Shell>
    )
  }
  if (!s) return <Shell state="ok" label="Loading…" />

  const change = s.spend.change_vs_prev_7_pct
  return (
    <Shell state={s.state} label={stateText(s)}>
      {s.attention.length > 0 && (
        <Section title="Needs you" accent>
          {s.attention.map((a) => (
            <Row key={`${a.kind}:${a.title}`} dot={a.severity} title={a.title} sub={a.detail}>
              <button className={btn} onClick={() => bridge.open(a.href)}>
                {a.kind.startsWith('session') ? 'Open' : 'Fix'}
              </button>
            </Row>
          ))}
        </Section>
      )}

      <Section title="Sessions">
        {s.sessions.map((x) => {
          const idle = s.attention.some((a) => a.kind === 'session_idle' && a.href === `/sessions?open=${x.name}`)
          return (
            <Row key={x.name} dot={!x.alive ? (x.exit_status ? 'problem' : 'ok') : idle ? 'attention' : 'ok'} mono title={x.name}
              sub={`${x.tool === 'codex' ? 'Codex' : 'Claude Code'} · ${shortPath(x.project ?? '').split('/').pop() || '~'} · ${!x.alive ? 'exited' : idle ? `idle ${x.idle_minutes} min` : 'running'}`}>
              <button className={ghost} onClick={() => bridge.open(`/sessions?open=${x.name}`)}>Open</button>
            </Row>
          )
        })}
        {!s.sessions.length && !picking && <p className="py-1 text-[12.5px] text-muted-foreground">No sessions running.</p>}
        {picking && !pending && (
          <div className="flex flex-col gap-1 pt-1">
            {s.recent_projects.map((p) => (
              <button key={p.path} onClick={() => preview(p.path, p.tool)}
                className="rounded-md border bg-card px-2.5 py-1.5 text-left font-mono text-[12px] hover:border-brand">
                {shortPath(p.path)} <span className="text-muted-foreground">· {p.tool === 'codex' ? 'Codex' : 'Claude Code'}</span>
              </button>
            ))}
            {!s.recent_projects.length && <p className="text-[12.5px] text-muted-foreground">No recent projects yet.</p>}
          </div>
        )}
        {pending && (
          <div className="flex flex-col gap-1.5 pt-1">
            <span className="eyebrow text-[10px]">Eyrie will run</span>
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-all rounded-md border bg-tint px-2.5 py-1.5 font-mono text-[11px] leading-relaxed">
              {pending.error ?? (pending.argv ? '$ ' + pending.argv.join(' ') : '…')}
            </pre>
            <div className="flex gap-2">
              <button className={btn} disabled={!pending.argv || !!pending.error} onClick={start}>Start session</button>
              <button className={ghost} onClick={() => setPending(null)}>Back</button>
            </div>
          </div>
        )}
      </Section>

      <Section title="Today">
        <div className="flex items-center gap-3">
          <span className="font-mono text-[22px] leading-none tracking-[-0.03em]">{fmtUsd(s.spend.today)}</span>
          <div className="min-w-0 flex-1">
            <Sparkline height={34} format={fmtUsd} points={s.spend.last_7_days.map((d) => ({ label: d.day, value: d.cost }))} />
          </div>
        </div>
        <p className="text-[12px] text-muted-foreground">
          {change === null ? 'No earlier week to compare' : `${change >= 0 ? '+' : '−'}${Math.abs(change).toFixed(0)}% vs previous 7 days`}
        </p>
      </Section>

      {task !== null && (
        <form className="flex gap-2 border-t px-4 py-2.5" onSubmit={(e) => { e.preventDefault(); addTask() }}>
          <input autoFocus value={task} onChange={(e) => setTask(e.target.value)} placeholder="Add to Personal/Tasks.md"
            className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 text-[13px]" aria-label="New task" />
          <button className={btn} type="submit" disabled={!task.trim()}>Add</button>
        </form>
      )}
      {note && <p className="border-t px-4 py-2 text-[12px] text-muted-foreground">{note}</p>}

      <footer className="flex flex-wrap items-center gap-1.5 border-t px-4 py-2.5">
        <button className={btn} onClick={() => { setPicking((p) => !p); setPending(null) }}>{picking ? 'Cancel' : '+ Session in…'}</button>
        <button className={btn} onClick={() => setTask((t) => (t === null ? '' : null))}>+ Task</button>
        <button className={`${btn} ml-auto border-primary bg-primary text-primary-foreground hover:bg-primary/90`} onClick={() => bridge.open('/')}>
          Open Eyrie
        </button>
      </footer>
      {settings && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t px-4 py-2 text-[12px] text-muted-foreground">
          <label className="inline-flex items-center gap-1.5">
            <input type="checkbox" checked={settings.autostart}
              onChange={(e) => bridge.setAutostart(e.target.checked).then(() => setSettings({ ...settings, autostart: e.target.checked }))} />
            Start at login
          </label>
          {settings.platform === 'macos' && (
            <label className="inline-flex items-center gap-1.5">
              <input type="checkbox" checked={settings.show_cost}
                onChange={(e) => bridge.setShowCost(e.target.checked).then(() => setSettings({ ...settings, show_cost: e.target.checked }))} />
              Cost in menu bar
            </label>
          )}
          <button className="ml-auto hover:text-foreground" onClick={() => bridge.quit()}>Quit</button>
        </div>
      )}
    </Shell>
  )
}

function Shell({ state, label, children }: { state: string; label: string; children?: React.ReactNode }) {
  return (
    <div className="flex h-screen flex-col overflow-y-auto bg-background text-foreground">
      <header className="flex items-center gap-2.5 border-b px-4 py-3">
        <span className="flex size-[22px] items-center justify-center rounded-md bg-primary text-[12px] font-bold text-primary-foreground">
          e<span className="text-brand">.</span>
        </span>
        <span className="font-semibold tracking-[-0.01em]">Eyrie</span>
        <span className="ml-auto inline-flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
          <Dot tone={state} />
          {label}
        </span>
      </header>
      {children}
    </div>
  )
}

function Section({ title, accent, children }: { title: string; accent?: boolean; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-0.5 border-b px-4 py-2.5 last:border-b-0">
      <span className={`eyebrow mb-1 flex items-center gap-1.5 text-[10px] ${accent ? 'text-brand' : ''}`}>
        {accent && <span className="size-1.5 rounded-full bg-brand" />}
        {title}
      </span>
      {children}
    </section>
  )
}

function Row({ dot, title, sub, mono, children }: { dot: string; title: string; sub?: string; mono?: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5 py-1">
      <Dot tone={dot} />
      <div className="min-w-0 flex-1">
        <div className={`truncate text-[13px] font-medium ${mono ? 'font-mono text-[12.5px]' : ''}`}>{title}</div>
        {sub && <div className="truncate text-[11.5px] text-muted-foreground">{sub}</div>}
      </div>
      {children}
    </div>
  )
}
