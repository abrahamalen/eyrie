import { useEffect, useState, type ReactNode } from 'react'
import { Check, Copy, Moon, Sun } from 'lucide-react'
import { cn } from 'cn'

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      aria-label={`${label}: ${text}`}
      className="inline-flex items-center gap-1.5 self-start rounded-md px-1 py-0.5 text-[13px] font-medium text-brand hover:underline"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        } catch {
          // Clipboard can be refused (e.g. an insecure context); the text is on screen to select.
        }
      }}
    >
      {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
      <span aria-live="polite">{copied ? 'Copied' : label}</span>
    </button>
  )
}

/** A command box with a Copy button under it. */
export function Command({ text, copy = text, wrap }: { text: string; copy?: string; wrap?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <pre className={cn('cmd m-0', wrap && 'break-words whitespace-pre-wrap')}>{text}</pre>
      <CopyButton text={copy} />
    </div>
  )
}

export function Eyebrow({ children, accent, dot, className }: { children: ReactNode; accent?: boolean; dot?: boolean; className?: string }) {
  return (
    <span className={cn('eyebrow inline-flex items-center gap-2.5 text-[12px]', accent && 'text-brand', className)}>
      {dot && <span className="size-1.5 rounded-full bg-brand" aria-hidden />}
      {children}
    </span>
  )
}

export function ButtonLink({ href, children, primary, external }: { href: string; children: ReactNode; primary?: boolean; external?: boolean }) {
  return (
    <a
      href={href}
      {...(external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium whitespace-nowrap no-underline transition-colors',
        primary ? 'border-primary bg-primary text-primary-foreground hover:opacity-90' : 'bg-card hover:bg-accent',
      )}
    >
      {children}
    </a>
  )
}

const THEME_KEY = 'eyrie-landing-theme'

/** Follows the OS until you pick; the pick is remembered (index.html applies it before paint). */
export function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'))
  useEffect(() => {
    const mq = matchMedia('(prefers-color-scheme: dark)')
    const follow = (e: MediaQueryListEvent) => {
      let saved: string | null = null
      try {
        saved = localStorage.getItem(THEME_KEY)
      } catch {
        /* storage blocked */
      }
      if (!saved) setDark(e.matches)
    }
    mq.addEventListener('change', follow)
    return () => mq.removeEventListener('change', follow)
  }, [])
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])
  return (
    <button
      type="button"
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      className="inline-flex size-9 items-center justify-center rounded-lg border bg-card text-muted-foreground hover:bg-accent hover:text-foreground"
      onClick={() => {
        const next = !dark
        setDark(next)
        try {
          localStorage.setItem(THEME_KEY, next ? 'dark' : 'light')
        } catch {
          /* storage blocked: the toggle still works for this visit */
        }
      }}
    >
      {dark ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
    </button>
  )
}
