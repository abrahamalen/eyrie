import { useEffect, useState } from 'react'
import { FilePlus } from 'lucide-react'
import { api, StaleError } from '@/api/client'
import type { NexusFile } from '@/api/types'
import { usePoll } from '@/usePoll'
import { fmtAgo } from '@/format'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

type Sel = { agent: string; name: string }
const same = (a: Sel | null, b: Sel | null) => !!a && !!b && a.agent === b.agent && a.name === b.name

function Notice({ tone, children }: { tone: 'warn' | 'ok' | 'bad'; children: React.ReactNode }) {
  const cls = {
    warn: 'border-amber-500/60 bg-amber-500/10',
    ok: 'border-emerald-600/40 bg-emerald-600/5',
    bad: 'border-destructive/40 bg-destructive/5 text-destructive',
  }[tone]
  return <div role="status" className={`flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm ${cls}`}>{children}</div>
}

export function NexusPage() {
  const list = usePoll(api.nexus, 15_000)
  const [sel, setSel] = useState<Sel | null>(null)
  const [file, setFile] = useState<NexusFile | null>(null)
  const [draft, setDraft] = useState('')
  const [pendingSel, setPendingSel] = useState<Sel | null>(null)
  const [conflict, setConflict] = useState<NexusFile | null>(null)
  const [notice, setNotice] = useState<{ tone: 'ok' | 'bad' | 'warn'; text: string } | null>(null)
  const [creating, setCreating] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [busy, setBusy] = useState(false)
  const dirty = !!file && draft !== file.content

  const load = async (s: Sel, msg?: string) => {
    try {
      const f = await api.nexusFile.read(s.agent, s.name)
      setSel(s)
      setFile(f)
      setDraft(f.content)
      setConflict(null)
      setNotice(msg ? { tone: 'warn', text: msg } : null)
    } catch (e) {
      setNotice({ tone: 'bad', text: e instanceof Error ? e.message : String(e) })
    }
  }

  const open = (s: Sel) => {
    if (same(s, sel)) return
    if (dirty) setPendingSel(s)
    else load(s)
  }

  // Agents write to these files while they work. Check every 10s: reload quietly if there
  // are no local edits, otherwise flag the conflict before Save would hit it.
  useEffect(() => {
    if (!file) return
    const id = setInterval(async () => {
      try {
        const latest = await api.nexusFile.read(file.agent, file.name)
        if (latest.etag === file.etag) return
        if (draft === file.content) {
          setFile(latest)
          setDraft(latest.content)
          setNotice({ tone: 'warn', text: 'This file was changed outside Eyrie; showing the latest version.' })
        } else {
          setConflict(latest)
        }
      } catch {
        // deleted elsewhere or backend restarting; Save will report it
      }
    }, 10_000)
    return () => clearInterval(id)
  }, [file, draft])

  const save = async (etag: string) => {
    if (!file) return
    setBusy(true)
    try {
      const f = await api.nexusFile.write(file.agent, file.name, draft, etag)
      setFile(f)
      setDraft(f.content)
      setConflict(null)
      setNotice({ tone: 'ok', text: 'Saved.' })
      list.refresh()
    } catch (e) {
      if (e instanceof StaleError) setConflict(e.current as NexusFile)
      else setNotice({ tone: 'bad', text: `Couldn't save: ${e instanceof Error ? e.message : String(e)}` })
    } finally {
      setBusy(false)
    }
  }

  const create = async (agent: string) => {
    const name = newName.trim().endsWith('.md') ? newName.trim() : `${newName.trim()}.md`
    try {
      await api.nexusFile.write(agent, name, `# ${name.replace(/\.md$/, '')}\n\n`, 'absent')
      setCreating(null)
      setNewName('')
      await list.refresh()
      load({ agent, name })
    } catch (e) {
      setNotice({ tone: 'bad', text: e instanceof StaleError ? `${name} already exists.` : `Couldn't create: ${e instanceof Error ? e.message : String(e)}` })
    }
  }

  const agents = list.data?.agents ?? []

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Nexus memory</h1>
        <p className="text-sm text-muted-foreground">
          What Nexus agents remember, in your vault at agent-memory/Nexus. Edit or remove a memory here; deleted files
          go to the vault's .trash folder.
        </p>
      </div>
      {list.error && <p className="text-sm text-destructive">Couldn't reach backend: {list.error}</p>}

      <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <Card className="self-start">
          <CardContent className="flex flex-col gap-4">
            {!list.data && !list.error && <Skeleton className="h-40" />}
            {agents.map((a) => (
              <div key={a.agent} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-xs font-medium uppercase tracking-wide text-muted-foreground" title={a.agent}>
                    {a.agent.replace(/^nexus-/, '')}
                  </span>
                  <Button variant="ghost" size="icon" className="ml-auto size-6" aria-label={`New file in ${a.agent}`}
                    onClick={() => { setCreating(a.agent); setNewName('') }}>
                    <FilePlus className="size-3.5" />
                  </Button>
                </div>
                {creating === a.agent && (
                  <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); if (newName.trim()) create(a.agent) }}>
                    <Input id={`new-${a.agent}`} autoFocus value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="feedback_style.md" className="h-7 text-xs" />
                    <Button size="sm" type="submit" disabled={!newName.trim()}>Add</Button>
                  </form>
                )}
                {a.files.map((f) => {
                  const active = same(sel, { agent: a.agent, name: f.name })
                  return (
                    <button
                      key={f.name}
                      type="button"
                      aria-pressed={active}
                      onClick={() => open({ agent: a.agent, name: f.name })}
                      className="flex items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-muted aria-pressed:bg-muted aria-pressed:font-medium"
                    >
                      <span className="min-w-0 flex-1 truncate font-mono text-xs">{f.name}</span>
                      <span className="shrink-0 text-xs text-muted-foreground">{fmtAgo(f.modified)}</span>
                    </button>
                  )
                })}
                {!a.files.length && <span className="px-2 text-xs text-muted-foreground">No files</span>}
              </div>
            ))}
            {list.data && !agents.length && <p className="text-sm text-muted-foreground">No Nexus agents have saved memory yet.</p>}
          </CardContent>
        </Card>

        <Card>
          {!file ? (
            <CardContent className="flex flex-col gap-3">
              {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
              <p className="py-16 text-center text-sm text-muted-foreground">Pick a file on the left.</p>
            </CardContent>
          ) : (
            <>
              <CardHeader>
                <CardTitle className="font-mono text-sm">
                  {file.agent}/{file.name}
                  {dirty && <span className="ml-2 font-sans text-xs font-normal text-amber-600">unsaved</span>}
                </CardTitle>
                <CardDescription>
                  Modified {fmtAgo(file.modified)}
                  {file.linked_from.length > 0 && ` · linked from ${file.linked_from.join(', ')}`}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                {pendingSel && (
                  <Notice tone="warn">
                    <span className="flex-1">Discard your unsaved changes to {file.name}?</span>
                    <Button size="sm" variant="outline" onClick={() => setPendingSel(null)}>Keep editing</Button>
                    <Button size="sm" variant="destructive" onClick={() => { const s = pendingSel; setPendingSel(null); load(s) }}>Discard</Button>
                  </Notice>
                )}
                {conflict && (
                  <Notice tone="warn">
                    <span className="flex-1">
                      {file.name} changed since you opened it, probably because the agent wrote to it. Your edits are still
                      here.
                    </span>
                    <Button size="sm" variant="outline" onClick={() => load({ agent: file.agent, name: file.name })}>
                      Load their version
                    </Button>
                    <Button size="sm" variant="destructive" disabled={busy} onClick={() => save(conflict.etag)}>
                      Overwrite with mine
                    </Button>
                  </Notice>
                )}
                {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
                <textarea
                  id="nexus-editor"
                  aria-label={`Contents of ${file.name}`}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  spellCheck={false}
                  className="min-h-[28rem] w-full rounded-lg border bg-transparent p-3 font-mono text-xs leading-relaxed"
                />
                <div className="flex flex-wrap gap-2">
                  <Button disabled={!dirty || busy || !!conflict} onClick={() => save(file.etag)}>
                    {busy ? 'Saving…' : 'Save'}
                  </Button>
                  <Button variant="outline" disabled={!dirty} onClick={() => setDraft(file.content)}>
                    Revert
                  </Button>
                  <Button variant="ghost" className="ml-auto text-destructive" onClick={() => setDeleting(true)}>
                    Delete
                  </Button>
                </div>
              </CardContent>
            </>
          )}
        </Card>
      </div>

      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {file?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              Moves it to .trash/agent-memory/Nexus/{file?.agent}/ in your vault, so you can restore it.
              {file && file.linked_from.length > 0 &&
                ` ${file.linked_from.join(', ')} still links to it; update the index after deleting.`}
              {dirty && ' Your unsaved edits will be lost.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              onClick={async () => {
                if (!file) return
                try {
                  const r = await api.nexusFile.remove(file.agent, file.name, file.etag)
                  setDeleting(false)
                  setFile(null)
                  setSel(null)
                  list.refresh()
                  setNotice({ tone: 'ok', text: `Moved to ${r.trashed_to}.` })
                } catch (e) {
                  setDeleting(false)
                  if (e instanceof StaleError) setConflict(e.current as NexusFile)
                  else setNotice({ tone: 'bad', text: `Couldn't delete: ${e instanceof Error ? e.message : String(e)}` })
                }
              }}
            >
              Move to trash
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
