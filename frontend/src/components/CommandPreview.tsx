/** The exact command Eyrie will run, shown before any change is made. Secret values are
 * masked by the backend. */
export function CommandPreview({ argv, error }: { argv: string[] | null; error?: string | null }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="eyebrow">Eyrie will run</span>
      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : (
        <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border bg-tint px-3.5 py-2.5 font-mono text-xs leading-relaxed">
          {argv ? '$ ' + argv.map(quote).join(' ') : '…'}
        </pre>
      )}
    </div>
  )
}

function quote(a: string) {
  return /^[\w@%+=:,./~-]+$/.test(a) ? a : `'${a.replace(/'/g, `'\\''`)}'`
}

export function ResultLine({ result }: { result: { ok: boolean; message: string } | null }) {
  if (!result) return null
  return (
    <div
      role="status"
      className={`whitespace-pre-wrap rounded-md border px-3 py-2 text-sm ${
        result.ok ? 'border-emerald-600/40 bg-emerald-600/5' : 'border-destructive/40 bg-destructive/5 text-destructive'
      }`}
    >
      {result.message || (result.ok ? 'Done.' : 'Failed.')}
    </div>
  )
}
