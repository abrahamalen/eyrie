export interface ClaudeProject {
  path: string
  cost_usd: number
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_creation_tokens: number
  models: string[]
  last_start_time: string | null
}

export interface ClaudeUsage {
  projects: ClaudeProject[]
  totals: {
    cost_usd: number
    input_tokens: number
    output_tokens: number
    cache_read_tokens: number
    cache_creation_tokens: number
  }
  by_model: Record<string, { cost_usd: number; input_tokens: number; output_tokens: number }>
  enabled_plugins: string[]
  configured_mcp: { name: string; type: string; scope: string }[]
}

export interface CodexThread {
  id: string
  cwd: string
  model: string
  tokens_used: number
  updated_at: number
  reasoning_effort: string | null
  title: string
}

export interface CodexUsage {
  threads: CodexThread[]
  totals: { tokens_used: number }
  by_model: Record<string, number>
  by_cwd: Record<string, number>
  available: boolean
}

export type McpClient = 'claude' | 'codex'
export type McpScope = 'user' | 'local' | 'project'

export interface McpServer {
  name: string
  client: McpClient
  scope: McpScope
  type: string
  target: string
  project: string | null
}

export interface McpStatus {
  configured: McpServer[]
  last_known_failures: { name: string; status: string; detail: string }[]
}

export interface Plugin {
  id: string
  name: string
  marketplace: string
  version: string | null
  scope: string | null
  enabled: boolean
  projectEnabled: boolean | null
  installedAt: string | null
  lastUpdated: string | null
}

export interface ActionPreview {
  action: string
  argv: string[]
  destructive: boolean
  dry_run: true
}

export interface ActionResult {
  action: string
  argv: string[]
  ok: boolean
  exit_code: number
  message: string
  duration_ms: number
}

export interface AuditEntry {
  ts: string
  action: string
  argv: string[]
  params: Record<string, unknown>
  ok: boolean
  exit_code: number
  duration_ms: number
  message: string
}

export interface NexusAgent {
  agent: string
  file_count: number
  last_used: string
}

export interface Task {
  id: string
  done: boolean
  text: string
  line: number
}

export interface TasksSnapshot {
  etag: string
  tasks: Task[]
}

export interface UsageModel {
  model: string
  priced: boolean
  cost: number
  input: number
  output: number
  cache_read: number
  cache_write: number
  tokens: number
  messages: number
}

export interface UsageReport {
  range: { days: number; start: string; end: string }
  days: { day: string; models: Record<string, { cost: number; tokens: number }> }[]
  by_model: UsageModel[]
  by_project: { project: string; cost: number; tokens: number; sessions: number }[]
  totals: { cost: number; tokens: number; messages: number; sessions: number }
  codex: {
    available: boolean
    threads: number
    tokens: number
    by_model: { model: string; threads: number; tokens: number }[]
    error?: string
  }
  index: { files: number; messages: number; oldest: string | null; last_scan_ms: number }
  pricing: { updated: string; unpriced_models: string[] }
  note: string
}

export type SessionTool = 'claude' | 'codex'

export interface Session {
  name: string
  tool: SessionTool | null
  cwd: string | null
  mode: string | null
  conversation_id: string | null
  created: string | null
  last_output: string | null
  attached: number
  alive: boolean
  exit_status: number | null
  command: string | null
  attach: string
}

export interface SessionsSnapshot {
  sessions: Session[]
  dirs: string[]
  error: string | null
}

export interface Conversation {
  id: string
  started: string
  last: string
  messages: number
  project: string | null
}
