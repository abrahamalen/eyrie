import type { ClaudeUsage, CodexUsage, McpStatus, NexusAgent, TasksSnapshot, UsageReport } from './types'

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

/** The file changed on disk since it was read; `current` is what's there now. */
export class StaleError<T> extends Error {
  current: T
  constructor(current: T) {
    super('Changed on disk since it was loaded')
    this.current = current
  }
}

async function send<T>(method: string, path: string, body?: unknown, extra?: Record<string, string>): Promise<T> {
  const headers: Record<string, string> = { 'X-Eyrie-Token': await token(), ...extra }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!res.ok) {
    const err = await res.json().catch(() => null)
    if (err?.current) throw new StaleError<T>(err.current)
    throw new Error(err?.detail ?? `${method} ${path} -> ${res.status}`)
  }
  return res.json()
}

const source = <T>(id: string) => () => get<T>(`/api/v1/sources/${id}`)

export const api = {
  claude: source<ClaudeUsage>('claude'),
  codex: source<CodexUsage>('codex'),
  mcp: source<McpStatus>('mcp'),
  nexus: source<{ agents: NexusAgent[] }>('nexus'),
  usage: (days: number) => get<UsageReport>(`/api/v1/usage?days=${days}`),
  tasks: {
    list: () => get<TasksSnapshot>('/api/v1/tasks'),
    add: (etag: string, text: string) => send<TasksSnapshot>('POST', '/api/v1/tasks', { text }, { 'If-Match': etag }),
    update: (etag: string, id: string, patch: { done?: boolean; text?: string }) =>
      send<TasksSnapshot>('PATCH', `/api/v1/tasks/${id}`, patch, { 'If-Match': etag }),
    remove: (etag: string, id: string) => send<TasksSnapshot>('DELETE', `/api/v1/tasks/${id}`, undefined, { 'If-Match': etag }),
  },
}
