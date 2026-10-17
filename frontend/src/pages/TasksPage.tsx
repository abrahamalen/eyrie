import { useState } from 'react'
import { X } from 'lucide-react'
import { api } from '@/api/client'
import { usePoll } from '@/usePoll'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

export function TasksPage() {
  const { data, refresh } = usePoll(api.tasks.list, 15_000)
  const [input, setInput] = useState('')
  const tasks = data ?? []

  const onAdd = async () => {
    if (!input.trim()) return
    await api.tasks.add(input.trim())
    setInput('')
    refresh()
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Tasks</h1>
        <p className="text-sm text-muted-foreground">
          Stored as a plain checklist in your vault at Personal/Tasks.md, so you can edit it in Obsidian too.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Checklist</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            {tasks.map((t, i) => (
              <div
                key={i}
                className="group flex items-start gap-3 rounded-md px-2 py-1.5 hover:bg-muted/50"
              >
                <Checkbox
                  checked={t.done}
                  onCheckedChange={() => api.tasks.toggle(i).then(refresh)}
                  className="mt-0.5"
                />
                <span className={`flex-1 text-sm ${t.done ? 'text-muted-foreground line-through' : ''}`}>
                  {t.text}
                </span>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6 opacity-0 group-hover:opacity-100"
                  onClick={() => api.tasks.remove(i).then(refresh)}
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            ))}
            {!tasks.length && <div className="text-sm italic text-muted-foreground">No tasks yet — add one below.</div>}
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
