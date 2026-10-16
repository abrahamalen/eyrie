import type { ClaudeUsage, CodexUsage, McpStatus, NexusAgent, Task } from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

export const api = {
  claude: () => get<ClaudeUsage>('/api/claude'),
  codex: () => get<CodexUsage>('/api/codex'),
  mcp: () => get<McpStatus>('/api/mcp'),
  nexus: () => get<{ agents: NexusAgent[] }>('/api/nexus'),
  tasks: {
    list: () => get<Task[]>('/api/tasks'),
    add: (text: string) =>
      fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }).then((r) => r.json() as Promise<Task[]>),
    toggle: (index: number) =>
      fetch(`/api/tasks/${index}/toggle`, { method: 'POST' }).then((r) => r.json() as Promise<Task[]>),
    remove: (index: number) =>
      fetch(`/api/tasks/${index}`, { method: 'DELETE' }).then((r) => r.json() as Promise<Task[]>),
  },
}
