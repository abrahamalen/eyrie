import { useState } from 'react'
import { api, type SnoozeFor } from '@/api/client'
import type { Idle } from '@/api/types'
import { fmtIdle, fmtTokens } from '@/format'

/** `idle 2 d 3 h`, amber; grey when snoozed or dismissed. Nothing when not idle. */
export function IdleBadge({ idle }: { idle: Idle | null | undefined }) {
  if (!idle?.idle) return null
  const quiet = !!idle.snoozed_until || idle.dismissed
  const label = idle.snoozed_until ? 'snoozed · ' : idle.dismissed ? 'not suggested · ' : ''
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-px text-xs font-medium ${
        quiet ? 'bg-muted text-muted-foreground' : 'bg-amber-500/15 text-amber-800 dark:text-amber-300'
      }`}
      title={idle.snoozed_until ? `Snoozed until ${new Date(idle.snoozed_until).toLocaleString()}` : `No activity since ${new Date(idle.since).toLocaleString()}`}
    >
      {label}idle {idle.exact ? '' : '~'}{fmtIdle(idle.minutes)}
    </span>
  )
}

/** docs/stop-and-idle.md §3.3, word for word: only when the backend says it applies. */
export function ContextHint({ idle }: { idle: Idle | null | undefined }) {
  if (!idle?.compact_command || !idle.context_tokens) return null
  return (
    <div className="mt-1.5 max-w-[62ch] whitespace-normal border-l-2 border-brand pl-2 text-xs text-muted-foreground">
      Idle sessions don't use tokens. Its prompt cache has expired, so your next message re-reads{' '}
      {fmtTokens(idle.context_tokens)} of context. Run <code className="rounded bg-muted px-1 font-mono">{idle.compact_command}</code> first, or start fresh.
    </div>
  )
}

const SNOOZE: [SnoozeFor, string][] = [
  ['1d', 'For a day'],
  ['7d', 'For a week'],
  ['dismiss', "Don't suggest until it's used again"],
]

/** Snooze or dismiss one session's suggestion; "Suggest again" undoes it. */
export function SnoozeSelect({ idle, name, onDone }: {
  idle: Pick<Idle, 'idle' | 'key' | 'snoozed_until' | 'dismissed'> | null | undefined; name: string; onDone: (note: string) => void
}) {
  const [busy, setBusy] = useState(false)
  if (!idle?.idle) return null
  const quiet = !!idle.snoozed_until || idle.dismissed
  const run = async (fn: () => Promise<unknown>, note: string) => {
    setBusy(true)
    try {
      await fn()
      onDone(note)
    } catch (e) {
      onDone(`Couldn't snooze: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(false)
    }
  }
  if (quiet) {
    return (
      <button type="button" disabled={busy} className="h-7 rounded-md border bg-transparent px-2 text-xs hover:bg-accent"
        onClick={() => run(() => api.suggestions.clear(idle.key), `Suggesting ${name} again.`)}>
        Suggest again
      </button>
    )
  }
  return (
    <select
      aria-label={`Snooze ${name}`}
      className="h-7 w-28 rounded-md border bg-transparent px-1 text-xs"
      value=""
      disabled={busy}
      onChange={(e) => {
        const how = e.target.value as SnoozeFor
        const label = SNOOZE.find(([k]) => k === how)?.[1] ?? ''
        if (how) run(() => api.suggestions.snooze(idle.key, how), how === 'dismiss' ? `Won't suggest ${name} again until it's used.` : `Snoozed ${name} ${label.toLowerCase()}.`)
      }}
    >
      <option value="">Snooze…</option>
      {SNOOZE.map(([k, v]) => (
        <option key={k} value={k}>{v}</option>
      ))}
    </select>
  )
}
