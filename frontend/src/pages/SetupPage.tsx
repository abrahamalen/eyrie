import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, X } from 'lucide-react'
import { api, StaleError } from '@/api/client'
import type { SetupBody, SetupState } from '@/api/types'
import { shortPath } from '@/format'
import { setMeta } from '@/tools'
import { Logo } from '@/components/Logo'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

type Draft = { tools: Set<string>; roots: string[]; tasks: string }

const STEPS = ['Tools', 'Where you work', 'Tasks', 'Review'] as const

function fromState(s: SetupState): Draft {
  return { tools: new Set(s.tools.filter((t) => t.enabled).map((t) => t.id)), roots: s.roots, tasks: s.tasks ?? '' }
}

/** "auto" while every detected tool is ticked, so a tool installed later appears by itself. */
function toBody(s: SetupState, d: Draft): SetupBody {
  const detected = s.tools.filter((t) => t.installed || t.used).map((t) => t.id)
  const auto = detected.length === d.tools.size && detected.every((t) => d.tools.has(t))
  return {
    tools_enabled: auto ? 'auto' : s.tools.filter((t) => d.tools.has(t.id)).map((t) => t.id),
    roots: d.roots,
    tasks: d.tasks.trim() || null,
  }
}

function ToolsStep({ state, draft, setDraft }: StepProps) {
  return (
    <div className="flex flex-col divide-y">
      {state.tools.map((t) => {
        const available = t.installed || t.used
        return (
          <label key={t.id} className={`flex items-center gap-3 py-3 ${available ? '' : 'opacity-60'}`}>
            <Checkbox
              checked={draft.tools.has(t.id)}
              onCheckedChange={(on) => {
                const next = new Set(draft.tools)
                if (on) next.add(t.id)
                else next.delete(t.id)
                setDraft({ ...draft, tools: next })
              }}
            />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">
                {t.title} {t.version && <span className="font-mono text-xs text-muted-foreground">{t.version}</span>}
              </div>
              <div className="truncate font-mono text-xs text-muted-foreground">
                {t.installed ? shortPath(t.path ?? '') : 'not on your PATH'}
                {t.home && ` · ${shortPath(t.home)} ${t.used ? 'found' : 'not found'}`}
              </div>
            </div>
          </label>
        )
      })}
    </div>
  )
}

function RootsStep({ state, draft, setDraft }: StepProps) {
  const [input, setInput] = useState('')
  const add = (p: string) => {
    const v = p.trim()
    if (v && !draft.roots.includes(v)) setDraft({ ...draft, roots: [...draft.roots, v] })
  }
  const suggestions = state.suggested_roots.filter((r) => !draft.roots.includes(r.path))
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Sessions can start in any folder under these, plus any project your tools already know.
      </p>
      <div className="flex flex-wrap gap-1.5">
        {draft.roots.map((r) => (
          <span key={r} className="inline-flex items-center gap-1 rounded-full border bg-background py-0.5 pl-2.5 pr-1 font-mono text-[12.5px]">
            {shortPath(r)}
            <button type="button" aria-label={`Remove ${r}`} className="rounded-full p-0.5 hover:bg-muted"
              onClick={() => setDraft({ ...draft, roots: draft.roots.filter((x) => x !== r) })}>
              <X className="size-3" />
            </button>
          </span>
        ))}
        {!draft.roots.length && <span className="text-sm text-muted-foreground">None yet.</span>}
      </div>
      {suggestions.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="eyebrow mr-1 text-[10.5px]">Suggested</span>
          {suggestions.map((r) => (
            <button key={r.path} type="button" onClick={() => add(r.path)}
              className="rounded-full border border-dashed px-2.5 py-0.5 font-mono text-[12.5px] hover:border-brand hover:text-brand">
              + {shortPath(r.path)} <span className="text-muted-foreground">· {r.projects} projects</span>
            </button>
          ))}
        </div>
      )}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); add(input); setInput('') }}>
        <Input id="setup-root" value={input} onChange={(e) => setInput(e.target.value)} placeholder="/Users/you/code" autoComplete="off" />
        <Button type="submit" variant="outline" disabled={!input.trim()}>Add</Button>
      </form>
    </div>
  )
}

function TasksStep({ state, draft, setDraft }: StepProps) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted-foreground">
        Optional. A markdown checklist Eyrie shows on the Tasks page; it edits only the lines you change, so the file
        stays yours. Leave empty to skip.
      </p>
      <Input id="setup-tasks" value={draft.tasks} onChange={(e) => setDraft({ ...draft, tasks: e.target.value })}
        placeholder="/Users/you/notes/Tasks.md" autoComplete="off" />
      {state.obsidian_vaults.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="eyebrow mr-1 text-[10.5px]">Obsidian vaults</span>
          {state.obsidian_vaults.map((v) => (
            // Fills only the folder: a vault can hold several task lists (say, one for work), so the
            // file is always yours to name.
            <button key={v} type="button"
              onClick={() => {
                setDraft({ ...draft, tasks: `${v}/` })
                document.getElementById('setup-tasks')?.focus()
              }}
              className="rounded-full border border-dashed px-2.5 py-0.5 font-mono text-[12.5px] hover:border-brand hover:text-brand">
              {shortPath(v)}/…
            </button>
          ))}
        </div>
      )}
      <p className="text-sm text-muted-foreground">
        Agent memory: {state.agent_memory.exists
          ? <>found at <span className="font-mono">{shortPath(state.agent_memory.path)}</span>, nothing to set.</>
          : <>none yet. It appears once a Claude Code subagent with memory writes to <span className="font-mono">{shortPath(state.agent_memory.path)}</span>.</>}
      </p>
    </div>
  )
}

function Review({ state, draft }: StepProps) {
  const body = toBody(state, draft)
  const rows: [string, React.ReactNode][] = [
    ['Tools', body.tools_enabled === 'auto'
      ? `Every tool found (${[...draft.tools].map((t) => state.tools.find((x) => x.id === t)?.title).join(', ') || 'none yet'})`
      : body.tools_enabled.map((t) => state.tools.find((x) => x.id === t)?.title).join(', ') || 'None'],
    ['Where you work', body.roots.length ? body.roots.map(shortPath).join(', ') : 'Only projects your tools know'],
    ['Tasks', body.tasks ? shortPath(body.tasks) : 'Off'],
  ]
  return (
    <div className="flex flex-col gap-3">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="min-w-0 break-words font-mono text-[13px]">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs text-muted-foreground">
        Saved to <span className="font-mono">{shortPath(state.config.path)}</span>
        {state.config.exists ? ', merged into what is there' : ''}. Applies at once; no restart.
      </p>
    </div>
  )
}

type StepProps = { state: SetupState; draft: Draft; setDraft: (d: Draft) => void }
const STEP_VIEWS = [ToolsStep, RootsStep, TasksStep, Review]

export function SetupPage({ firstRun }: { firstRun: boolean }) {
  const navigate = useNavigate()
  const [state, setState] = useState<SetupState | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  useEffect(() => {
    api.setup.get().then((s) => { setState(s); setDraft(fromState(s)) }).catch((e) => setNotice({ tone: 'error', text: String(e.message ?? e) }))
  }, [])

  const save = async () => {
    if (!state || !draft) return
    setBusy(true)
    try {
      const s = await api.setup.write(toBody(state, draft), state.config.etag)
      setState(s)
      setDraft(fromState(s))
      setMeta(await api.meta())
      if (firstRun) navigate('/', { replace: true })
      else setNotice({ tone: 'ok', text: `Saved to ${shortPath(s.config.path)}.` })
    } catch (e) {
      if (e instanceof StaleError) {
        const cur = e.current as SetupState
        setState(cur)
        setDraft(fromState(cur))
        setNotice({ tone: 'error', text: 'The config file changed since this page loaded, so nothing was saved. This shows what is there now.' })
      } else {
        setNotice({ tone: 'error', text: `Couldn't save: ${e instanceof Error ? e.message : String(e)}` })
      }
    } finally {
      setBusy(false)
    }
  }

  const notes = notice && (
    <p role="status" className={`text-sm ${notice.tone === 'error' ? 'text-destructive' : 'text-muted-foreground'}`}>{notice.text}</p>
  )
  if (!state || !draft) return <div className="p-6">{notes ?? <Skeleton className="h-64" />}</div>

  if (!firstRun) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader eyebrow="You" title="Settings" description={<>What Eyrie uses on this machine. Saved to {shortPath(state.config.path)}.</>} />
        {STEP_VIEWS.slice(0, 3).map((View, i) => (
          <Card key={STEPS[i]}>
            <CardHeader><CardTitle>{STEPS[i]}</CardTitle></CardHeader>
            <CardContent><View state={state} draft={draft} setDraft={setDraft} /></CardContent>
          </Card>
        ))}
        <div className="flex items-center gap-3">
          <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
          {notes}
        </div>
      </div>
    )
  }

  const View = STEP_VIEWS[step]
  return (
    <div className="mx-auto flex min-h-svh max-w-2xl flex-col justify-center gap-6 px-4 py-10">
      <div className="flex items-center justify-between">
        <Logo tagline={false} />
        <span className="eyebrow text-[10.5px]">First run</span>
      </div>
      <Card>
        <CardHeader className="gap-3">
          <ol className="flex flex-wrap gap-1.5" aria-label="Setup steps">
            {STEPS.map((s, i) => (
              <li key={s} aria-current={i === step ? 'step' : undefined}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12.5px] ${i === step ? 'border-foreground font-medium' : 'text-muted-foreground'}`}>
                {i < step ? <Check className="size-3" /> : <span className="font-mono">{i + 1}</span>} {s}
              </li>
            ))}
          </ol>
          <h2 className="text-xl font-semibold tracking-tight">
            {['Which tools do you use?', 'Where do you work?', 'A tasks file?', 'This is what Eyrie will save.'][step]}
          </h2>
          <CardDescription>
            {['Eyrie found these. Untick any you don\'t want it to manage.', '', '', ''][step]}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <View state={state} draft={draft} setDraft={setDraft} />
          <div className="flex items-center justify-between gap-3 border-t pt-4">
            <Button variant="ghost" onClick={() => setStep(step - 1)} disabled={step === 0}>Back</Button>
            {step < STEPS.length - 1
              ? <Button onClick={() => setStep(step + 1)}>Next</Button>
              : <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save and open Eyrie'}</Button>}
          </div>
          {notes}
        </CardContent>
      </Card>
    </div>
  )
}
