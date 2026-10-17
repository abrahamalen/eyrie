import type { ClaudeUsage, CodexUsage, McpStatus, NexusAgent, Task } from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

// The backend only accepts writes carrying the per-install token; it hands that token
// out to same-origin pages on this machine.
let tokenPromise: Promise<string> | null = null
function token(): Promise<string> {
  tokenPromise ??= get<{ token: string }>('/api/v1/auth/token')
    .then((r) => r.token)
    .catch((e) => {
      tokenPromise = null
      throw e
    })
  return tokenPromise
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'X-Eyrie-Token': await token() }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}`)
  return res.json()
}

const source = <T>(id: string) => () => get<T>(`/api/v1/sources/${id}`)

export const api = {
  claude: source<ClaudeUsage>('claude'),
  codex: source<CodexUsage>('codex'),
  mcp: source<McpStatus>('mcp'),
  nexus: source<{ agents: NexusAgent[] }>('nexus'),
  tasks: {
    list: () => get<Task[]>('/api/v1/tasks'),
    add: (text: string) => send<Task[]>('POST', '/api/v1/tasks', { text }),
    toggle: (index: number) => send<Task[]>('POST', `/api/v1/tasks/${index}/toggle`),
    remove: (index: number) => send<Task[]>('DELETE', `/api/v1/tasks/${index}`),
  },
}
