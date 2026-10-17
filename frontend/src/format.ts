const HOME = '/Users/alenabraham'

export function fmtNum(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('en-US')
}

export function fmtUsd(n: number | null | undefined): string {
  return '$' + (n ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function shortPath(p: string): string {
  return p.startsWith(HOME) ? '~' + p.slice(HOME.length) : p
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
