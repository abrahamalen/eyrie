import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import type { ActionResult, Session } from '@/api/types'
import { CommandPreview, ResultLine } from '@/components/CommandPreview'
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

/** Page-level so polling can drop the session's row without closing this dialog. */
export function StopSessionDialog({ session, onClose }: { session: Session | null; onClose: (stopped: boolean) => void }) {
  const [argv, setArgv] = useState<string[] | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [shown, setShown] = useState<Session | null>(null)
  if (session && session !== shown) {
    setShown(session)
    setArgv(null)
    setResult(null)
  }
  const name = session?.name

  useEffect(() => {
    if (name) api.actions.preview('sessions.stop', { name }).then((p) => setArgv(p.argv))
  }, [name])

  const s = shown
  const label = s?.alive ? 'Stop' : 'Close'
  return (
    <AlertDialog open={!!session} onOpenChange={(o) => !o && onClose(!!result?.ok)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {label} {s?.name}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            {s?.alive
              ? `Ends the ${s.tool === 'codex' ? 'Codex' : 'Claude Code'} process and its tmux session. The conversation stays on disk and can be resumed.`
              : 'The process has already exited. This removes the finished tmux session and its scrollback.'}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <CommandPreview argv={argv} />
        <ResultLine result={result} />
        <AlertDialogFooter>
          <AlertDialogCancel>{result?.ok ? 'Close' : 'Cancel'}</AlertDialogCancel>
          {!result?.ok && s && (
            <Button
              variant="destructive"
              disabled={busy || !argv}
              onClick={async () => {
                setBusy(true)
                try {
                  setResult(await api.actions.run('sessions.stop', { name: s.name }, true))
                } catch (e) {
                  setResult({ action: 'sessions.stop', argv: [], ok: false, exit_code: -1, duration_ms: 0, message: e instanceof Error ? e.message : String(e) })
                } finally {
                  setBusy(false)
                }
              }}
            >
              {busy ? 'Stopping…' : `${label} session`}
            </Button>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
