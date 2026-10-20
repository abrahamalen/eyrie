import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { token } from '@/api/client'
import type { Session } from '@/api/types'
import { CopyButton } from '@/components/CopyButton'
import { Button } from '@/components/ui/button'

type Status = { state: 'connecting' | 'connected' | 'closed'; reason?: string }

const encoder = new TextEncoder()

/** Interactive terminal attached to the session's tmux server. Closing it only detaches. */
export function SessionTerminal({ session }: { session: Session }) {
  const host = useRef<HTMLDivElement>(null)
  const [readonly, setReadonly] = useState(false)
  const [status, setStatus] = useState<Status>({ state: 'connecting' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const el = host.current
    if (!el) return
    const term = new Terminal({
      cursorBlink: !readonly,
      disableStdin: readonly,
      fontFamily: '"Geist Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 13,
      scrollback: 5000,
      theme: { background: '#0a0a0a', foreground: '#e5e5e5' },
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(el)
    fit.fit()

    let ws: WebSocket | null = null
    let closed = false
    const sendSize = () => {
      if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
    }
    const ro = new ResizeObserver(() => {
      fit.fit()
      sendSize()
    })
    ro.observe(el)

    setStatus({ state: 'connecting' })
    token()
      .then((t) => {
        if (closed) return
        const proto = location.protocol === 'https:' ? 'wss' : 'ws'
        ws = new WebSocket(
          `${proto}://${location.host}/api/v1/sessions/${session.name}/term?cols=${term.cols}&rows=${term.rows}${readonly ? '&readonly=true' : ''}`,
          ['eyrie', `eyrie.token.${t}`],
        )
        ws.binaryType = 'arraybuffer'
        ws.onopen = () => {
          setStatus({ state: 'connected' })
          sendSize()
          if (!readonly) term.focus()
        }
        ws.onmessage = (e) => term.write(new Uint8Array(e.data as ArrayBuffer))
        ws.onclose = (e) => {
          if (!closed) setStatus({ state: 'closed', reason: e.reason || (e.code === 1000 ? 'Session detached or ended' : `Closed (${e.code})`) })
        }
        term.onData((d) => {
          if (ws?.readyState === WebSocket.OPEN) ws.send(encoder.encode(d))
        })
      })
      .catch((e) => setStatus({ state: 'closed', reason: `Couldn't get the access token: ${e.message}` }))

    return () => {
      closed = true
      ro.disconnect()
      ws?.close()
      term.dispose()
    }
  }, [session.name, readonly, attempt])

  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="bg-[#0a0a0a] p-2">
        <div ref={host} className="h-[26rem]" aria-label={`Terminal for ${session.name}`} />
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t bg-card px-3 py-2 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span
            className={`size-2 rounded-full ${
              status.state === 'connected' ? 'bg-emerald-500' : status.state === 'connecting' ? 'bg-amber-500' : 'bg-muted-foreground/50'
            }`}
          />
          {status.state === 'connected'
            ? readonly
              ? 'Watching (input off)'
              : 'Connected: you are typing into this session'
            : status.state === 'connecting'
              ? 'Connecting…'
              : status.reason}
        </span>
        {status.state === 'closed' && (
          <Button variant="outline" size="sm" onClick={() => setAttempt((a) => a + 1)}>
            Reconnect
          </Button>
        )}
        <label className="inline-flex items-center gap-1.5">
          <input id={`readonly-${session.name}`} type="checkbox" checked={readonly} onChange={(e) => setReadonly(e.target.checked)} />
          Watch only
        </label>
        <span className="ml-auto inline-flex flex-wrap items-center gap-2">
          <span>Closing this only detaches. From a terminal:</span>
          <code className="rounded bg-muted px-1.5 py-0.5 text-foreground">{session.attach}</code>
          <CopyButton text={session.attach} />
        </span>
      </div>
    </div>
  )
}
