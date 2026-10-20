// Stopping sessions and describing what they cost (docs/stop-and-idle.md).
import { api } from '@/api/client'
import type { ActionResult, ExternalSession, Idle, Resources } from '@/api/types'
import { fmtAgo, fmtBytes, fmtIdle, fmtTokens, shortPath, toolTitle } from '@/format'

export function stopParams(x: ExternalSession, force = false) {
  return { pid: x.pid, tool: x.tool, tty: x.tty, started: x.process_started, force }
}

/** sessions.stop_external, confirmed; errors (409s) come back as a failed result. */
export async function stopExternal(x: ExternalSession, force = false): Promise<ActionResult> {
  try {
    return await api.actions.run('sessions.stop_external', stopParams(x, force), true)
  } catch (e) {
    return { action: 'sessions.stop_external', argv: [], ok: false, exit_code: -1, duration_ms: 0,
      message: e instanceof Error ? e.message : String(e), state: null }
  }
}

/** "Claude Code · ~/p/eyrie · idle 2 d · iTerm2 on ttys004 · pid 4242" */
export function externalMeta(x: ExternalSession) {
  const when = x.idle ? (x.idle.idle ? `idle ${x.idle.exact ? '' : '~'}${fmtIdle(x.idle.minutes)}` : `active ${fmtAgo(x.idle.since)}`) : null
  return [toolTitle(x.tool), x.cwd ? shortPath(x.cwd) : null, when, `${x.terminal ?? 'a terminal'} on ${x.tty}`, `pid ${x.pid}`]
    .filter(Boolean).join(' · ')
}

/** "~410 MB · 3 child processes · ~142k tokens of context" */
export function costLine(resources: Resources | null | undefined, idle?: Pick<Idle, 'context_tokens'> | null): string {
  const parts = []
  if (resources?.rss_bytes) parts.push(fmtBytes(resources.rss_bytes))
  const n = resources?.child_processes
  if (n) parts.push(`${n} child process${n === 1 ? '' : 'es'}`)
  if (idle?.context_tokens) parts.push(`${fmtTokens(idle.context_tokens)} of context`)
  return parts.join(' · ')
}
