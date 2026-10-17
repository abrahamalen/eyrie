import type {
  ActionPreview,
  ActionResult,
  AuditEntry,
  ClaudeUsage,
  Conversation,
  CodexUsage,
  McpStatus,
  NexusAgent,
  NexusFile,
  Plugin,
  SessionsSnapshot,
  TasksSnapshot,
  UsageReport,
} from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${path} -> ${res.status}`)
  return res.json()
}

// The backend only accepts writes carrying the per-install token; it hands that token
// out to same-origin pages on this machine.
let tokenPromise: Promise<string> | null = null
export function token(): Promise<string> {
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
    // FastAPI puts a message in `detail`; some errors nest it one level down.
    const detail = typeof err?.detail === 'object' ? err.detail?.detail : err?.detail
    throw new Error(detail ?? `${method} ${path} -> ${res.status}`)
  }
  return res.json()
}

const source = <T>(id: string) => () => get<T>(`/api/v1/sources/${id}`)
const enc = encodeURIComponent

export const api = {
  claude: source<ClaudeUsage>('claude'),
  codex: source<CodexUsage>('codex'),
  mcp: source<McpStatus>('mcp'),
  nexus: source<{ agents: NexusAgent[] }>('nexus'),
  nexusFile: {
    read: (agent: string, name: string) => get<NexusFile>(`/api/v1/nexus/${enc(agent)}/${enc(name)}`),
    write: (agent: string, name: string, content: string, etag: string) =>
      send<NexusFile>('PUT', `/api/v1/nexus/${enc(agent)}/${enc(name)}`, { content }, { 'If-Match': etag }),
    remove: (agent: string, name: string, etag: string) =>
      send<{ trashed_to: string }>('DELETE', `/api/v1/nexus/${enc(agent)}/${enc(name)}`, undefined, { 'If-Match': etag }),
  },
  usage: (days: number) => get<UsageReport>(`/api/v1/usage?days=${days}`),
  plugins: source<{ plugins: Plugin[]; error: string | null }>('plugins'),
  sessions: {
    list: source<SessionsSnapshot>('sessions'),
    screen: (name: string, lines = 200) =>
      get<{ name: string; text: string }>(`/api/v1/sessions/${name}/screen?lines=${lines}`),
    conversations: (limit = 15) => get<Conversation[]>(`/api/v1/sessions/conversations?limit=${limit}`),
  },
  audit: (limit = 200) => get<AuditEntry[]>(`/api/v1/audit?limit=${limit}`),
  actions: {
    preview: (id: string, params: object) =>
      send<ActionPreview>('POST', `/api/v1/actions/${id}`, { params, dry_run: true }),
    run: (id: string, params: object, confirm = false) =>
      send<ActionResult>('POST', `/api/v1/actions/${id}`, { params, confirm }),
  },
  tasks: {
    list: () => get<TasksSnapshot>('/api/v1/tasks'),
    add: (etag: string, text: string) => send<TasksSnapshot>('POST', '/api/v1/tasks', { text }, { 'If-Match': etag }),
    update: (etag: string, id: string, patch: { done?: boolean; text?: string }) =>
      send<TasksSnapshot>('PATCH', `/api/v1/tasks/${id}`, patch, { 'If-Match': etag }),
    remove: (etag: string, id: string) => send<TasksSnapshot>('DELETE', `/api/v1/tasks/${id}`, undefined, { 'If-Match': etag }),
  },
}
