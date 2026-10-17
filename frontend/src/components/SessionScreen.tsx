import { useEffect, useRef } from 'react'
import { api } from '@/api/client'
import type { Session } from '@/api/types'
import { usePoll } from '@/usePoll'
import { CopyButton } from '@/components/CopyButton'

/** Read-only view of a session's screen, refreshed every 2 seconds. */
export function SessionScreen({ session }: { session: Session }) {
  const { data, error } = usePoll(() => api.sessions.screen(session.name, 300), 2_000, session.name)
  const pre = useRef<HTMLPreElement>(null)
  const pinned = useRef(true)

  useEffect(() => {
    const el = pre.current
    if (el && pinned.current) el.scrollTop = el.scrollHeight
  }, [data?.text])

  return (
    <div className="overflow-hidden rounded-lg border">
      <pre
        ref={pre}
        onScroll={(e) => {
          const el = e.currentTarget
          pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
        }}
        aria-label={`Screen of ${session.name}`}
        className="h-80 overflow-auto whitespace-pre bg-neutral-950 p-3 font-mono text-xs leading-relaxed text-neutral-100"
      >
        {error ? `Couldn't read the screen: ${error}` : (data?.text ?? 'Loading…')}
      </pre>
      <div className="flex flex-wrap items-center gap-2 border-t bg-card px-3 py-2 text-xs text-muted-foreground">
        <span>Read-only preview. To type into it, attach from a terminal:</span>
        <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">{session.attach}</code>
        <CopyButton text={session.attach} />
      </div>
    </div>
  )
}
