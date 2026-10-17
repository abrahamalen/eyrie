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

export interface McpStatus {
  configured: { name: string; type: string; scope: string }[]
  last_known_failures: { name: string; status: string; detail: string }[]
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
