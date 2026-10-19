// What each tool can do on this machine, from /api/v1/meta (loaded once at startup, like the
// home directory). Pickers offer only tools that are installed and have the capability.
import type { ToolInfo } from '@/api/types'

let tools: ToolInfo[] = []
// Assume configured until /meta says otherwise, so a backend that's down never forces setup.
let configured = true

export function setConfigured(c: boolean) {
  configured = c
}

export function isConfigured(): boolean {
  return configured
}

export function setTools(t: ToolInfo[]) {
  tools = t
}

export function toolInfo(id: string | null | undefined): ToolInfo | undefined {
  return tools.find((t) => t.id === id)
}

/** Installed tools that can run Eyrie sessions. */
export function sessionTools(): ToolInfo[] {
  return tools.filter((t) => t.installed && t.session_modes.length > 0)
}

/** Installed tools with MCP support. */
export function mcpTools(): ToolInfo[] {
  return tools.filter((t) => t.installed && t.mcp)
}

/** Tools worth showing in "your setup": installed, or used (their state folder exists). */
export function setupTools(): ToolInfo[] {
  return tools.filter((t) => t.installed || t.used)
}
