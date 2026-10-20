// The panel's only way out: Rust commands in widget/src-tauri (which hold the token and
// talk to 127.0.0.1). Nothing here does HTTP.
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import type { Summary } from '@/api/types'

export type WidgetSettings = { show_cost: boolean; autostart: boolean; platform: string; base_url: string; home: string }
export type ActionResponse = { status: number; body: { argv?: string[]; ok?: boolean; message?: string; detail?: unknown } }

const real = {
  summary: () => invoke<Summary>('summary'),
  refresh: () => invoke<Summary>('refresh'),
  action: (id: string, params: object, opts: { dry_run?: boolean; confirm?: boolean } = {}) =>
    invoke<ActionResponse>('action', { id, params, dryRun: !!opts.dry_run, confirm: !!opts.confirm }),
  addTask: (text: string) => invoke('add_task', { text }),
  open: (path: string) => invoke('open_eyrie', { path }),
  settings: () => invoke<WidgetSettings>('get_settings'),
  setShowCost: (on: boolean) => invoke('set_show_cost', { on }),
  setAutostart: (on: boolean) => invoke('set_autostart', { on }),
  startEyrie: () => invoke<string>('start_eyrie'),
  hide: () => invoke('hide'),
  quit: () => invoke('quit'),
  onSummary: (fn: (s: Summary) => void) => listen<Summary>('summary', (e) => fn(e.payload)),
  onUnreachable: (fn: (err: string) => void) => listen<string>('unreachable', (e) => fn(e.payload)),
}

// Development only: outside Tauri (e.g. a browser on the Vite dev server) read the summary
// through Vite's /api proxy so the panel can be checked visually. Stripped from production
// builds, so the shipped panel never does HTTP itself.
const inTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
const devFallback: typeof real = {
  ...real,
  summary: () => fetch('/api/v1/summary').then((r) => r.json()),
  refresh: () => fetch('/api/v1/summary').then((r) => r.json()),
  settings: async () => ({ show_cost: true, autostart: true, platform: 'macos', base_url: 'dev', home: '' }),
  action: async (_id, params) => ({ status: 200, body: { argv: ['(dev preview)', JSON.stringify(params)] } }),
  onSummary: async () => () => {},
  onUnreachable: async () => () => {},
}

export const bridge = import.meta.env.DEV && !inTauri ? devFallback : real
