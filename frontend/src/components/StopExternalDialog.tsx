import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import type { ActionResult, ExternalSession } from '@/api/types'
import { CommandPreview, ResultLine } from '@/components/CommandPreview'
import { CopyButton } from '@/components/CopyButton'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { externalMeta, stopExternal, stopParams } from '@/lib/stop'

export function ResumeBlock({ command, tool }: { command: string | null; tool: string }) {
  if (!command) {
    const cont = tool === 'codex' ? 'codex resume --last' : tool === 'gemini' ? 'gemini --resume latest' : 'claude --continue'
    return (
      <p className="text-sm text-muted-foreground">
        Eyrie doesn't know which conversation this is, so it can't give you a resume command;{' '}
        <code className="rounded bg-muted px-1 font-mono text-xs">{cont}</code> in that folder picks up the newest.
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-1">
      <span className="text-sm">The conversation is saved; resume it later with:</span>
      <div className="flex items-start gap-2">
        <code className="min-w-0 flex-1 break-all rounded-md border bg-muted px-2 py-1 font-mono text-xs">{command}</code>
        <CopyButton text={command} label="Copy" />
      </div>
    </div>
  )
}

/** docs/stop-and-idle.md §6.3: SIGTERM to one listed pid, then (only if it lingers) Force. */
export function StopExternalDialog({ session, onClose }: { session: ExternalSession | null; onClose: (stopped: boolean) => void }) {
  const [shown, setShown] = useState<ExternalSession | null>(null)
  const [force, setForce] = useState(false)
  const [argv, setArgv] = useState<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [busy, setBusy] = useState(false)
  if (session && session !== shown) {
    setShown(session)
    setForce(false)
    setArgv(null)
    setError(null)
    setResult(null)
  }
  const x = shown
  const pid = session?.pid

  useEffect(() => {
    if (!x || !pid) return
    api.actions.preview('sessions.stop_external', stopParams(x, force))
      .then((p) => setArgv(p.argv))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    // Only re-preview when the session or the signal changes, not on every poll.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid, force])

  const stopped = !!result && ['exited', 'already_exited'].includes(result.state ?? '')
  const lingering = !!result && result.state === 'still_running' && !force
  const kids = x?.resources.child_processes ?? 0
  return (
    <AlertDialog open={!!session} onOpenChange={(o) => !o && !busy && onClose(stopped)}>
      <AlertDialogContent className="max-h-[calc(100vh-2rem)] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>{force ? 'Force stop' : 'Stop'} {x?.display_name}?</AlertDialogTitle>
          <AlertDialogDescription>{x ? externalMeta(x) : ''}</AlertDialogDescription>
        </AlertDialogHeader>
        {x && (
          <div className="flex flex-col gap-3 text-sm">
            {force ? (
              <p>SIGKILL ends it immediately; anything it hasn't written yet is lost. Eyrie signals only pid {x.pid}.</p>
            ) : (
              <>
                <p>Eyrie sends SIGTERM to this one process (not its terminal, not its process group).</p>
                <ResumeBlock command={x.resume_command} tool={x.tool} />
                {kids > 0 && (
                  <p className="text-muted-foreground">
                    It has {kids} child process{kids === 1 ? '' : 'es'} (MCP servers and the like). Eyrie won't signal them; if any outlive the session, you'll see their pids.
                  </p>
                )}
              </>
            )}
          </div>
        )}
        <CommandPreview argv={argv} error={error} />
        <ResultLine result={result} />
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>{result ? 'Close' : 'Cancel'}</AlertDialogCancel>
          {lingering && (
            <Button variant="destructive" onClick={() => { setForce(true); setResult(null); setArgv(null) }}>
              Force stop…
            </Button>
          )}
          {!result && x && (
            <Button
              variant="destructive"
              disabled={busy || !argv || !!error}
              onClick={async () => {
                setBusy(true)
                setResult(await stopExternal(x, force))
                setBusy(false)
              }}
            >
              {busy ? (force ? 'Killing…' : 'Stopping…') : force ? 'Force stop' : 'Stop session'}
            </Button>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
