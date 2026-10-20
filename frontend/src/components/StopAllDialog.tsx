import { useState } from 'react'
import { api } from '@/api/client'
import type { ExternalSession, Session } from '@/api/types'
import { CopyButton } from '@/components/CopyButton'
import { IdleBadge } from '@/components/IdleBits'
import { stopExternal } from '@/lib/stop'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { fmtAgo, fmtBytes, shortPath, toolTitle } from '@/format'

type Row = { key: string; managed?: Session; external?: ExternalSession }
type Status = { tone: 'ok' | 'warn' | 'bad'; text: string; force?: boolean }

function rowOf(r: Row) {
  const s = (r.managed ?? r.external)!
  return { s, idle: s.idle, name: s.display_name }
}

/** docs/stop-and-idle.md §6.5: every live session, most idle first; only the suggested ones
 *  start ticked. Each stop is its own action (own checks, own audit entry), one at a time. */
export function StopAllDialog({ open, sessions, external, threshold, onClose }: {
  open: boolean; sessions: Session[]; external: ExternalSession[]; threshold: number; onClose: () => void
}) {
  const [rows, setRows] = useState<Row[] | null>(null)
  const [ticks, setTicks] = useState<Record<string, boolean>>({})
  const [status, setStatus] = useState<Record<string, Status>>({})
  const [busy, setBusy] = useState(false)
  const [ran, setRan] = useState(false)
  // Freeze the list when the dialog opens, so polling can't reorder or drop rows mid-run.
  if (open && rows === null) {
    const all: Row[] = [
      ...sessions.filter((s) => s.alive).map((s) => ({ key: `eyrie:${s.name}`, managed: s })),
      ...external.map((x) => ({ key: x.idle?.key ?? `pid:${x.pid}`, external: x })),
    ].sort((a, b) => (rowOf(b).idle?.minutes ?? -1) - (rowOf(a).idle?.minutes ?? -1))
    setRows(all)
    setTicks(Object.fromEntries(all.map((r) => [r.key, !!rowOf(r).idle?.suggested])))
    setStatus({})
    setRan(false)
  }
  if (!open && rows !== null) setRows(null)

  const stopOne = async (r: Row, force = false): Promise<Status> => {
    if (r.managed) {
      try {
        const res = await api.actions.run('sessions.stop', { name: r.managed.name }, true)
        return { tone: res.ok ? 'ok' : 'bad', text: res.ok ? `Stopped ${r.managed.name}.` : res.message }
      } catch (e) {
        return { tone: 'bad', text: e instanceof Error ? e.message : String(e) }
      }
    }
    const res = await stopExternal(r.external!, force)
    if (res.state === 'still_running') return { tone: 'warn', text: res.message, force: true }
    return { tone: res.ok ? 'ok' : 'bad', text: res.message }
  }
  const runAll = async () => {
    setBusy(true)
    for (const r of rows ?? []) {
      if (!ticks[r.key]) continue
      setStatus((m) => ({ ...m, [r.key]: { tone: 'warn', text: 'Stopping…' } }))
      const st = await stopOne(r)
      setStatus((m) => ({ ...m, [r.key]: st }))
    }
    setBusy(false)
    setRan(true)
  }
  const n = (rows ?? []).filter((r) => ticks[r.key]).length

  return (
    <AlertDialog open={open} onOpenChange={(o) => !o && !busy && onClose()}>
      <AlertDialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto sm:max-w-xl">
        <AlertDialogHeader>
          <AlertDialogTitle>Stop idle sessions</AlertDialogTitle>
          <AlertDialogDescription>
            Ticked: idle for {threshold} h or more and not snoozed. Each is stopped on its own, with the same checks as a single stop.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="flex flex-col">
          {(rows ?? []).map((r) => {
            const { s, idle, name } = rowOf(r)
            const st = status[r.key]
            const resume = s.resume_command
            return (
              <label key={r.key} className="grid grid-cols-[20px_minmax(0,1fr)] items-start gap-2.5 border-b py-2.5 last:border-b-0">
                <Checkbox
                  aria-label={`Stop ${name}`}
                  checked={!!ticks[r.key]}
                  disabled={busy || ran}
                  onCheckedChange={(v) => setTicks((t) => ({ ...t, [r.key]: !!v }))}
                  className="mt-1"
                />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{name}</span>
                    {idle?.idle ? <IdleBadge idle={idle} /> : (
                      <span className="text-xs text-muted-foreground">{idle ? `active ${fmtAgo(idle.since)}` : 'activity unknown'}</span>
                    )}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {toolTitle(s.tool)} · {s.cwd ? shortPath(s.cwd) : '—'}{s.resources.rss_bytes ? ` · ${fmtBytes(s.resources.rss_bytes)}` : ''}
                  </div>
                  {resume ? <CopyButton text={resume} label="Resume command" /> : (
                    <div className="text-xs text-muted-foreground">No resume command (conversation unknown)</div>
                  )}
                  {st && (
                    <div role="status" className={`mt-1 whitespace-pre-wrap text-xs ${st.tone === 'ok' ? 'text-emerald-700 dark:text-emerald-400' : st.tone === 'warn' ? 'text-amber-700 dark:text-amber-300' : 'text-destructive'}`}>
                      {st.text}
                      {st.force && r.external && (
                        <Button size="sm" variant="destructive" className="ml-2" onClick={async (e) => {
                          e.preventDefault()
                          setStatus((m) => ({ ...m, [r.key]: { tone: 'warn', text: 'Killing…' } }))
                          const done = await stopOne(r, true)
                          setStatus((m) => ({ ...m, [r.key]: done }))
                        }}>
                          Force stop
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              </label>
            )
          })}
          {rows && !rows.length && <p className="py-3 text-sm text-muted-foreground">No running sessions.</p>}
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{ran ? 'Close' : 'Cancel'}</AlertDialogCancel>
          {!ran && (
            <Button variant="destructive" disabled={busy || !n} onClick={runAll}>
              {busy ? 'Stopping…' : `Stop ${n} session${n === 1 ? '' : 's'}`}
            </Button>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
