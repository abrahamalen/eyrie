import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import type { ActionResult, McpServer } from '@/api/types'
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

function paramsOf(m: McpServer) {
  return { client: m.client, name: m.name, scope: m.scope, ...(m.project ? { project_dir: m.project } : {}) }
}

/** Page-level so polling can drop the server's row without closing this dialog. */
export function RemoveMcpDialog({ server, onClose }: { server: McpServer | null; onClose: (removed: boolean) => void }) {
  const [argv, setArgv] = useState<string[] | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [shown, setShown] = useState<McpServer | null>(null)
  if (server && server !== shown) {
    setShown(server)
    setArgv(null)
    setPreviewError(null)
    setResult(null)
  }
  const key = server ? JSON.stringify(paramsOf(server)) : null

  useEffect(() => {
    if (key) {
      api.actions.preview('mcp.remove', JSON.parse(key)).then((p) => setArgv(p.argv)).catch((e) => setPreviewError(e.message))
    }
  }, [key])

  const m = shown
  return (
    <AlertDialog open={!!server} onOpenChange={(o) => !o && onClose(!!result?.ok)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {m?.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            Removes it from {m?.client === 'codex' ? 'Codex' : 'Claude Code'} ({m?.scope} scope). Running sessions keep
            their connection until they restart. You can add it back later.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <CommandPreview argv={argv} error={previewError} />
        <ResultLine result={result} />
        <AlertDialogFooter>
          <AlertDialogCancel>{result?.ok ? 'Close' : 'Cancel'}</AlertDialogCancel>
          {!result?.ok && m && (
            <Button
              variant="destructive"
              disabled={busy || !argv}
              onClick={async () => {
                setBusy(true)
                try {
                  setResult(await api.actions.run('mcp.remove', paramsOf(m), true))
                } catch (e) {
                  setResult({ action: 'mcp.remove', argv: [], ok: false, exit_code: -1, duration_ms: 0, message: e instanceof Error ? e.message : String(e) })
                } finally {
                  setBusy(false)
                }
              }}
            >
              {busy ? 'Removing…' : 'Remove server'}
            </Button>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
