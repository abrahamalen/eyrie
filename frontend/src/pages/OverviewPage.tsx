import { Link } from 'react-router-dom'
import { Bot, Cloud, Plug, SquareCheck, SquareTerminal } from 'lucide-react'
import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { fmtUsd, shortPath } from '@/format'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'

const tagColors: Record<string, string> = {
  'Claude Code': 'text-blue-600 dark:text-blue-400',
  Codex: 'text-violet-600 dark:text-violet-400',
  MCP: 'text-emerald-600 dark:text-emerald-400',
  Nexus: 'text-amber-600 dark:text-amber-400',
}

export function OverviewPage() {
  const claude = usePoll(api.claude, 10_000)
  const codex = usePoll(api.codex, 10_000)
  const mcp = usePoll(api.mcp, 10_000)
  const nexus = usePoll(() => api.nexus(), 15_000)
  const tasks = usePoll(api.tasks.list, 15_000)

  const loading = !claude.data || !codex.data || !mcp.data || !nexus.data || !tasks.data

  const mcpFailed = mcp.data?.last_known_failures.length ?? 0
  const mcpOk = mcp.data
    ? mcp.data.configured.length - mcp.data.configured.filter((m) => mcp.data!.last_known_failures.some((f) => f.name === m.name)).length
    : 0
  const openTasks = tasks.data ? tasks.data.tasks.filter((t) => !t.done).length : 0
  const latestThread = codex.data?.threads[0]

  const stats = [
    { to: '/claude', icon: SquareTerminal, color: 'text-blue-600 dark:text-blue-400', value: claude.data ? fmtUsd(claude.data.totals.cost_usd) : '—', label: 'Claude Code' },
    { to: '/codex', icon: Cloud, color: 'text-violet-600 dark:text-violet-400', value: codex.data ? String(codex.data.threads.length) : '—', label: 'Codex threads' },
    { to: '/mcp', icon: Plug, color: mcpFailed ? 'text-red-600 dark:text-red-400' : 'text-emerald-600 dark:text-emerald-400', value: mcp.data ? `${mcpOk} ok` : '—', label: 'MCP servers' },
    { to: '/nexus', icon: Bot, color: 'text-amber-600 dark:text-amber-400', value: nexus.data ? String(nexus.data.agents.length) : '—', label: 'Nexus agents' },
    { to: '/tasks', icon: SquareCheck, color: 'text-slate-600 dark:text-slate-400', value: tasks.data ? String(openTasks) : '—', label: 'Open tasks' },
  ]

  return (
    <div className="flex flex-col gap-6">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/5 via-transparent to-primary/10 px-8 py-10">
        <h1 className="text-4xl font-bold tracking-tight">Your agents, at a glance</h1>
        <p className="mt-3 max-w-xl text-muted-foreground">
          Eyrie watches Claude Code, Codex, their MCP connectors, and Nexus agents live — no manual refresh, no
          snapshots.
        </p>
        <div className="mt-4 flex flex-wrap gap-x-2 gap-y-1 text-sm font-medium">
          {Object.entries(tagColors).map(([label, color], i) => (
            <span key={label} className="flex items-center gap-2">
              {i > 0 && <span className="text-muted-foreground">·</span>}
              <span className={color}>{label}</span>
            </span>
          ))}
        </div>
      </div>

      {mcpFailed > 0 && !loading && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm">
          <Badge variant="destructive">
            {mcpFailed} MCP server{mcpFailed === 1 ? '' : 's'} last known failing
          </Badge>
          <Link to="/mcp" className="text-muted-foreground underline underline-offset-2 hover:text-foreground">
            view details
          </Link>
        </div>
      )}

      {/* Unified stat strip */}
      {loading ? (
        <Skeleton className="h-28" />
      ) : (
        <div className="grid grid-cols-2 divide-y rounded-2xl border sm:grid-cols-5 sm:divide-y-0 sm:divide-x">
          {stats.map((s) => (
            <Link
              to={s.to}
              key={s.to}
              className="flex flex-col gap-2 p-5 transition-colors hover:bg-muted/50"
            >
              <s.icon className={`size-4 ${s.color}`} />
              <div className="text-2xl font-bold tabular-nums tracking-tight">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </Link>
          ))}
        </div>
      )}

      {/* Recent activity, terminal-style */}
      {!loading && latestThread && (
        <div className="overflow-hidden rounded-xl border bg-zinc-950 font-mono text-sm shadow-sm">
          <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5">
            <span className="size-2.5 rounded-full bg-red-500/70" />
            <span className="size-2.5 rounded-full bg-yellow-500/70" />
            <span className="size-2.5 rounded-full bg-green-500/70" />
            <span className="ml-2 text-xs text-zinc-500">codex — most recent thread</span>
          </div>
          <div className="px-4 py-4 text-zinc-300">
            <span className="text-emerald-400">$</span> codex{' '}
            <span className="text-zinc-500">— {shortPath(latestThread.cwd)}</span>
            <div className="mt-2 text-zinc-100">"{latestThread.title}"</div>
          </div>
        </div>
      )}
    </div>
  )
}
