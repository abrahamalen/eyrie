import { useState } from 'react'
import { api } from '@/api/client'
import type { ActionResult, Plugin } from '@/api/types'
import { usePoll } from '@/usePoll'
import { ResultLine } from '@/components/CommandPreview'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { PageHeader } from '@/components/PageHeader'

export function PluginsPage() {
  const { data, error, refresh } = usePoll(api.plugins, 15_000)
  const [pending, setPending] = useState<string | null>(null)
  const [result, setResult] = useState<ActionResult | null>(null)

  // Enabling and disabling are reversible, so they run straight away; the command and its
  // result are shown here and kept in the activity log.
  const toggle = async (p: Plugin) => {
    setPending(p.id)
    try {
      const r = await api.actions.run(p.enabled ? 'plugins.disable' : 'plugins.enable', {
        plugin: p.id,
        ...(p.scope ? { scope: p.scope } : {}),
      })
      setResult({ ...r, message: `$ ${r.argv.join(' ')}\n${r.message || (r.ok ? 'Done.' : 'Failed.')}` })
      await refresh()
    } catch (e) {
      setResult({ action: '', argv: [], ok: false, exit_code: -1, duration_ms: 0, message: e instanceof Error ? e.message : String(e) })
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="Tools" title="Plugins" description={<>Claude Code plugins. Switching one runs claude plugin enable or disable; new sessions pick it up.</>} />

      {error && <p className="text-sm text-destructive">Couldn't reach backend: {error}</p>}
      {data?.error && <p className="text-sm text-destructive">Couldn't list plugins: {data.error}</p>}
      <ResultLine result={result} />

      <Card>
        <CardContent className="flex flex-col">
          {!data && !error && <Skeleton className="h-32" />}
          {data?.plugins.map((p) => (
            <div key={p.id} className="flex items-center gap-4 border-b py-3 last:border-b-0">
              <div className="min-w-0 flex-1">
                <div className="font-medium">
                  {p.name} <span className="font-normal text-muted-foreground">@{p.marketplace}</span>
                </div>
                <div className="text-xs text-muted-foreground">
                  {[p.version && `v${p.version}`, p.scope && `${p.scope} scope`,
                    p.lastUpdated && `updated ${new Date(p.lastUpdated).toLocaleDateString('en-GB')}`]
                    .filter(Boolean).join(' · ')}
                </div>
              </div>
              <span className="text-xs text-muted-foreground">{p.enabled ? 'Enabled' : 'Disabled'}</span>
              <Switch
                checked={p.enabled}
                disabled={pending !== null}
                onCheckedChange={() => toggle(p)}
                aria-label={`${p.enabled ? 'Disable' : 'Enable'} ${p.name}`}
              />
            </div>
          ))}
          {data && !data.plugins.length && !data.error && (
            <div className="py-6 text-center text-sm text-muted-foreground">No plugins installed.</div>
          )}
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        Installing and uninstalling aren't here yet: marketplace installs can ask you to approve a command, which needs
        its own confirmation flow.
      </p>
    </div>
  )
}
