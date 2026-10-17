import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import type { ActionResult, SessionTool } from '@/api/types'
import { shortPath } from '@/format'
import { CommandPreview, ResultLine } from '@/components/CommandPreview'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export interface StartRequest {
  tool: SessionTool
  cwd?: string
  mode?: 'new' | 'continue' | 'resume'
  resumeId?: string
  label?: string
}

const selectClass = 'h-8 w-full rounded-lg border bg-transparent px-2.5 text-sm'

function newName() {
  const b = crypto.getRandomValues(new Uint8Array(3))
  return 'eyrie-' + Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
}

/** Starts a Claude Code or Codex session in tmux. `request` opens it (null closes it). */
export function StartSessionDialog({
  request,
  dirs,
  onClose,
  onStarted,
}: {
  request: StartRequest | null
  dirs: string[]
  onClose: () => void
  onStarted: (name: string) => void
}) {
  const [tool, setTool] = useState<SessionTool>('claude')
  const [cwd, setCwd] = useState('')
  const [mode, setMode] = useState<'new' | 'continue' | 'resume'>('new')
  // Generated here so the preview shows exactly the command that will run.
  const [ids, setIds] = useState({ name: newName(), conversation: crypto.randomUUID() })
  const [preview, setPreview] = useState<{ argv: string[] | null; error: string | null }>({ argv: null, error: null })
  const [result, setResult] = useState<ActionResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [openFor, setOpenFor] = useState<StartRequest | null>(null)

  // Reset the form whenever a new request opens the dialog.
  if (request && request !== openFor) {
    setOpenFor(request)
    setTool(request.tool)
    setCwd(request.cwd ?? dirs[0] ?? '')
    setMode(request.mode ?? 'new')
    setIds({ name: newName(), conversation: crypto.randomUUID() })
    setResult(null)
  }

  const resuming = mode === 'resume'
  const params = {
    tool,
    cwd,
    mode,
    name: ids.name,
    ...(resuming ? { resume_id: openFor?.resumeId } : {}),
    ...(tool === 'claude' && mode === 'new' ? { conversation_id: ids.conversation } : {}),
  }
  const key = JSON.stringify(params)

  useEffect(() => {
    if (!request) return
    api.actions
      .preview('sessions.start', JSON.parse(key))
      .then((p) => setPreview({ argv: p.argv, error: null }))
      .catch((e) => setPreview({ argv: null, error: e.message }))
  }, [key, request])

  const options = cwd && !dirs.includes(cwd) ? [cwd, ...dirs] : dirs

  return (
    <Dialog open={!!request} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{resuming ? 'Resume in a new session' : 'New session'}</DialogTitle>
          <DialogDescription>
            {openFor?.label ??
              'Starts detached in tmux. It keeps running if Eyrie restarts; attach from a terminal any time.'}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          {!resuming && (
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Tool
                <select id="session-tool" className={selectClass} value={tool} onChange={(e) => setTool(e.target.value as SessionTool)}>
                  <option value="claude">Claude Code</option>
                  <option value="codex">Codex</option>
                </select>
              </label>
              <label className="flex flex-col gap-1.5 text-sm font-medium">
                Start from
                <select id="session-mode" className={selectClass} value={mode} onChange={(e) => setMode(e.target.value as 'new' | 'continue')}>
                  <option value="new">New conversation</option>
                  <option value="continue">Latest conversation here</option>
                </select>
              </label>
            </div>
          )}
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            <span>
              Directory <span className="font-normal text-muted-foreground">known projects and sessions.roots</span>
            </span>
            <select id="session-cwd" className={selectClass} value={cwd} onChange={(e) => setCwd(e.target.value)}>
              {options.map((d) => (
                <option key={d} value={d}>
                  {shortPath(d)}
                </option>
              ))}
            </select>
          </label>
          <CommandPreview argv={preview.argv} error={preview.error} />
          <ResultLine result={result} />
        </div>
        <DialogFooter>
          <Button
            disabled={busy || !preview.argv || !!result?.ok}
            onClick={async () => {
              setBusy(true)
              try {
                const r = await api.actions.run('sessions.start', params)
                setResult(r)
                if (r.ok) {
                  onStarted(ids.name)
                  setTimeout(onClose, 700)
                }
              } catch (e) {
                setResult({ action: 'sessions.start', argv: [], ok: false, exit_code: -1, duration_ms: 0, message: e instanceof Error ? e.message : String(e) })
              } finally {
                setBusy(false)
              }
            }}
          >
            {busy ? 'Starting…' : 'Start session'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
