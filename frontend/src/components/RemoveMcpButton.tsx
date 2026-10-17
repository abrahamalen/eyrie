import { useState } from 'react'
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
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'

export function RemoveMcpButton({ server, onDone }: { server: McpServer; onDone: () => void }) {
  const [argv, setArgv] = useState<string[] | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)
  const [busy, setBusy] = useState(false)
  const params = { client: server.client, name: server.name, scope: server.scope,
    ...(server.project ? { project_dir: server.project } : {}) }

  return (
    <AlertDialog
      onOpenChange={(open) => {
        // Refresh only once the dialog closes: refreshing first removes this row and the
        // dialog with it, before the result can be read.
        if (!open) {
          if (result?.ok) onDone()
          return
        }
        setResult(null)
        api.actions.preview('mcp.remove', params).then((p) => setArgv(p.argv)).catch((e) => setPreviewError(e.message))
      }}
    >
      <AlertDialogTrigger render={<Button variant="ghost" size="sm" className="text-destructive" />}>
        Remove
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove {server.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            Removes it from {server.client === 'claude' ? 'Claude Code' : 'Codex'} ({server.scope} scope). Running
            sessions keep their connection until they restart. You can add it back later.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <CommandPreview argv={argv} error={previewError} />
        <ResultLine result={result} />
        <AlertDialogFooter>
          <AlertDialogCancel>{result?.ok ? 'Close' : 'Cancel'}</AlertDialogCancel>
          {!result?.ok && (
            <Button
              variant="destructive"
              disabled={busy || !argv}
              onClick={async () => {
                setBusy(true)
                try {
                  const r = await api.actions.run('mcp.remove', params, true)
                  setResult(r)
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
