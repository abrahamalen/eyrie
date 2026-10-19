// What this machine has, from /api/v1/meta: loaded at startup and again whenever Settings
// saves. Pickers offer only installed tools with the capability; the sidebar shows only
// pages for things that exist here. Components subscribe with useMeta().
import { useSyncExternalStore } from 'react'
import type { Meta, ToolInfo } from '@/api/types'

type Features = Meta['features']

let tools: ToolInfo[] = []
let features: Features = { tasks: true, agent_memory: true, mcp: true, plugins: true }
// Assume configured until /meta says otherwise, so a backend that's down never forces setup.
let configured = true
let version = 0
const listeners = new Set<() => void>()

export function setMeta(m: Meta) {
  tools = m.tools
  features = m.features
  configured = m.configured
  version++
  listeners.forEach((l) => l())
}

/** Re-renders the caller when /meta is reloaded (e.g. after Settings saves). */
export function useMeta(): { tools: ToolInfo[]; features: Features } {
  useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => version,
  )
  return { tools, features }
}

export function isConfigured(): boolean {
  return configured
}

export function toolInfo(id: string | null | undefined): ToolInfo | undefined {
  return tools.find((t) => t.id === id)
}

/** Installed, enabled tools that can run Eyrie sessions. */
export function sessionTools(): ToolInfo[] {
  return tools.filter((t) => t.enabled && t.installed && t.session_modes.length > 0)
}

/** Installed, enabled tools with MCP support. */
export function mcpTools(): ToolInfo[] {
  return tools.filter((t) => t.enabled && t.installed && t.mcp)
}
