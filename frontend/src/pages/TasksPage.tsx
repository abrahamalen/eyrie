import { useState } from 'react'
import { X } from 'lucide-react'
import { api, StaleError } from '@/api/client'
import type { TasksSnapshot } from '@/api/types'
import { usePoll } from '@/usePoll'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { PageHeader } from '@/components/PageHeader'

export function TasksPage() {
  const { data, set } = usePoll(api.tasks.list, 15_000)
  const [input, setInput] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const tasks = data?.tasks ?? []

  // Every write sends the etag we last saw. If Obsidian changed the file in between, the
  // backend refuses and returns what's there now, so we show that instead of overwriting it.
  const write = async (fn: (etag: string) => Promise<TasksSnapshot>) => {
    if (!data) return false
    try {
      set(await fn(data.etag))
      setNotice(null)
      return true
    } catch (e) {
      if (e instanceof StaleError) {
        set(e.current as TasksSnapshot)
        setNotice('Tasks.md changed in Obsidian since this page loaded, so your change was not saved. The list now shows the latest version. Make the change again if you still need it.')
      } else {
        setNotice(`Couldn't save: ${e instanceof Error ? e.message : String(e)}`)
      }
      return false
    }
  }

  const onAdd = async () => {
    const text = input.trim()
    if (!text) return
    if (await write((etag) => api.tasks.add(etag, text))) setInput('')
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="You" title="Tasks" description={<>A plain markdown checklist (choose the file in Settings), so you can keep editing it anywhere, e.g. in Obsidian. Eyrie only changes the task lines you touch.</>} />

      {notice && (
        <div
          role="status"
          className="flex items-start gap-3 rounded-lg border border-amber-500/60 bg-amber-500/10 px-4 py-3 text-sm"
        >
          <span className="flex-1">{notice}</span>
          <Button variant="ghost" size="icon" className="size-6" aria-label="Dismiss" onClick={() => setNotice(null)}>
            <X className="size-3.5" />
          </Button>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Checklist</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            {tasks.map((t) => (
              <div key={t.id} className="group flex items-start gap-3 rounded-md px-2 py-1.5 hover:bg-muted/50">
                <Checkbox
                  checked={t.done}
                  onCheckedChange={() => write((etag) => api.tasks.update(etag, t.id, { done: !t.done }))}
                  className="mt-0.5"
                />
                <span className={`flex-1 text-sm ${t.done ? 'text-muted-foreground line-through' : ''}`}>
                  {t.text}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                  aria-label={`Delete "${t.text}"`}
                  onClick={() => write((etag) => api.tasks.remove(etag, t.id))}
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            ))}
            {data && !tasks.length && (
              <div className="text-sm italic text-muted-foreground">No tasks yet. Add one below.</div>
            )}
          </div>
          <Input
            placeholder="Add a task and press Enter…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onAdd()
            }}
          />
        </CardContent>
      </Card>
    </div>
  )
}
