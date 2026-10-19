import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '@/api/client'
import type { ActionResult, McpClient, McpScope } from '@/api/types'
import { CommandPreview, ResultLine } from '@/components/CommandPreview'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { mcpTools, toolInfo } from '@/tools'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

type Transport = 'stdio' | 'http' | 'sse'

const TRANSPORT_LABELS: Record<Transport, string> = { stdio: 'stdio (command)', http: 'http (URL)', sse: 'sse (URL)' }
const SCOPE_LABELS: Record<McpScope, string> = {
  user: 'user (all projects)',
  local: 'local (one project, private)',
  project: 'project (shared, in the repo)',
}

const selectClass = 'h-8 w-full rounded-lg border bg-transparent px-2.5 text-sm'

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium">
      <span>
        {label} {hint && <span className="font-normal text-muted-foreground">{hint}</span>}
      </span>
      {children}
    </label>
  )
}

// "KEY=value" / "Name: value" lines -> object. Blank lines ignored.
function pairs(text: string, sep: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    const i = line.indexOf(sep)
    if (i < 0) out[line.trim()] = ''
    else out[line.slice(0, i).trim()] = line.slice(i + 1).trim()
  }
  return out
}

export function AddMcpDialog({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const clients = mcpTools()
  const [client, setClient] = useState<McpClient>(clients[0]?.id ?? 'claude')
  const caps = toolInfo(client)?.mcp
  const [transport, setTransport] = useState<Transport>('stdio')
  const [scope, setScope] = useState<McpScope>('user')
  const [name, setName] = useState('')
  const [command, setCommand] = useState('')
  const [url, setUrl] = useState('')
  const [projectDir, setProjectDir] = useState('')
  const [env, setEnv] = useState('')
  const [headers, setHeaders] = useState('')
  const [bearer, setBearer] = useState('')
  const [preview, setPreview] = useState<{ argv: string[] | null; error: string | null }>({ argv: null, error: null })
  const [result, setResult] = useState<ActionResult | null>(null)
  const [busy, setBusy] = useState(false)

  const isStdio = transport === 'stdio'
  const [cmd, ...args] = command.trim().split(/\s+/).filter(Boolean)
  const params = {
    client,
    name: name.trim(),
    transport,
    scope,
    ...(scope !== 'user' && { project_dir: projectDir.trim() }),
    ...(isStdio
      ? { command: cmd ?? '', args, env: pairs(env, '=') }
      : { url: url.trim(), ...(caps?.headers ? { headers: pairs(headers, ':') } : {}),
          ...(caps?.bearer_token_env_var && bearer.trim() ? { bearer_token_env_var: bearer.trim() } : {}) }),
  }
  const key = JSON.stringify(params)

  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => {
      api.actions
        .preview('mcp.add', JSON.parse(key))
        .then((p) => setPreview({ argv: p.argv, error: null }))
        .catch((e) => setPreview({ argv: null, error: e.message }))
    }, 250)
    return () => clearTimeout(t)
  }, [key, open])

  const submit = async () => {
    setBusy(true)
    try {
      const r = await api.actions.run('mcp.add', params)
      setResult(r)
      if (r.ok) {
        onDone()
        setTimeout(() => setOpen(false), 900)
      }
    } catch (e) {
      setResult({ action: 'mcp.add', argv: [], ok: false, exit_code: -1, duration_ms: 0, message: String(e instanceof Error ? e.message : e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) setResult(null) }}>
      <DialogTrigger render={<Button />}>
        <Plus className="size-4" /> Add server
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Add MCP server</DialogTitle>
          <DialogDescription>
            Eyrie runs the client's own CLI. It never edits config files directly.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (!preview.error) submit()
          }}
        >
          <div className="grid grid-cols-2 gap-3">
            <Field label="Client">
              <select id="mcp-client" className={selectClass} value={client} onChange={(e) => {
                const next = e.target.value as McpClient
                setClient(next)
                // Keep the scope and transport valid for the new client.
                const c = toolInfo(next)?.mcp
                if (c && !c.scopes.includes(scope)) setScope(c.scopes[0])
                if (c && !c.transports.includes(transport)) setTransport(c.transports[0])
              }}>
                {clients.map((t) => (
                  <option key={t.id} value={t.id}>{t.title}</option>
                ))}
              </select>
            </Field>
            <Field label="Name">
              <Input id="mcp-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="sqlite" autoComplete="off" />
            </Field>
            <Field label="Transport">
              <select id="mcp-transport" className={selectClass} value={transport} onChange={(e) => setTransport(e.target.value as Transport)}>
                {(caps?.transports ?? ['stdio']).map((t) => (
                  <option key={t} value={t}>{TRANSPORT_LABELS[t]}</option>
                ))}
              </select>
            </Field>
            <Field label="Scope">
              <select id="mcp-scope" className={selectClass} value={scope} disabled={(caps?.scopes.length ?? 1) < 2}
                onChange={(e) => setScope(e.target.value as McpScope)}>
                {(caps?.scopes ?? ['user']).map((s) => (
                  <option key={s} value={s}>{SCOPE_LABELS[s]}</option>
                ))}
              </select>
            </Field>
          </div>
          {scope !== 'user' && (
            <Field label="Project directory" hint="absolute path">
              <Input id="mcp-project" value={projectDir} onChange={(e) => setProjectDir(e.target.value)} placeholder="/Users/you/personal/projects/eyrie" autoComplete="off" />
            </Field>
          )}
          {isStdio ? (
            <>
              <Field label="Command" hint="arguments split on spaces">
                <Input id="mcp-command" value={command} onChange={(e) => setCommand(e.target.value)} placeholder="uvx mcp-server-sqlite --db-path ~/notes.db" autoComplete="off" />
              </Field>
              <Field label="Environment" hint="one KEY=value per line, optional">
                <textarea id="mcp-env" rows={2} className="rounded-lg border bg-transparent px-2.5 py-1.5 font-mono text-xs" value={env} onChange={(e) => setEnv(e.target.value)} />
              </Field>
            </>
          ) : (
            <>
              <Field label="URL">
                <Input id="mcp-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/mcp" autoComplete="off" />
              </Field>
              {caps?.headers ? (
                <Field label="Headers" hint="one Name: value per line, optional">
                  <textarea id="mcp-headers" rows={2} className="rounded-lg border bg-transparent px-2.5 py-1.5 font-mono text-xs" value={headers} onChange={(e) => setHeaders(e.target.value)} />
                </Field>
              ) : (
                <Field label="Bearer token env var" hint="optional">
                  <Input id="mcp-bearer" value={bearer} onChange={(e) => setBearer(e.target.value)} placeholder="MY_SERVER_TOKEN" autoComplete="off" />
                </Field>
              )}
            </>
          )}
          <CommandPreview argv={preview.argv} error={preview.error} />
          <ResultLine result={result} />
          <DialogFooter>
            <Button type="submit" disabled={busy || !!preview.error || !preview.argv}>
              {busy ? 'Adding…' : 'Add server'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
