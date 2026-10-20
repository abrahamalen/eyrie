import { toolInfo } from '@/tools'

// Set from /api/v1/meta at startup; until then paths are shown in full.
let home = ''
export function setHome(h: string) {
  home = h.replace(/\/+$/, '')
}

export function fmtNum(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('en-US')
}

/** "1 session", "2 sessions"; pass `many` for irregular plurals. */
export function fmtCount(n: number | null | undefined, one: string, many = `${one}s`): string {
  return `${fmtNum(n)} ${(n ?? 0) === 1 ? one : many}`
}

export function fmtUsd(n: number | null | undefined): string {
  return '$' + (n ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** Shortens every home path inside free text, e.g. a server's command line. */
export function tildify(text: string): string {
  return home ? text.split(home + '/').join('~/') : text
}

export function shortPath(p: string): string {
  if (!home) return p
  if (p === home) return '~'
  return p.startsWith(home + '/') ? '~' + p.slice(home.length) : p
}

export function fmtCompact(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('en-US', { notation: 'compact', maximumFractionDigits: 1 })
}

export function fmtAgo(iso: string | null | undefined): string {
  if (!iso) return '—'
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

// Display names for tool ids: from /meta once loaded, else these; unknown ids show as themselves.
const TOOL_TITLES: Record<string, string> = { claude: 'Claude Code', codex: 'Codex', gemini: 'Gemini CLI' }

export function toolTitle(tool: string | null | undefined): string {
  return tool ? (toolInfo(tool)?.title ?? TOOL_TITLES[tool] ?? tool) : 'Unknown tool'
}

/** "45 min", "26 h", "2 d 3 h": how long a session has been idle. */
export function fmtIdle(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)} h`
  const h = Math.round((minutes % 1440) / 60)
  return `${Math.floor(minutes / 1440)} d${h ? ` ${h} h` : ''}`
}

/** "~410 MB", "~1.2 GB": RSS is an upper bound, so it's always approximate. */
export function fmtBytes(n: number | null | undefined): string {
  const mb = (n ?? 0) / 1024 / 1024
  return mb >= 1000 ? `~${(mb / 1024).toFixed(1)} GB` : `~${Math.max(1, Math.round(mb))} MB`
}

/** "~142k tokens". */
export function fmtTokens(n: number): string {
  return `~${n >= 1000 ? `${Math.round(n / 1000)}k` : n} tokens`
}
