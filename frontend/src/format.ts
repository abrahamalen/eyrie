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
