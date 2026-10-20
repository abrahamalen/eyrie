import type { ReactNode } from 'react'
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Bot,
  ChartColumnStacked,
  Eye,
  FileCheck,
  KeyRound,
  ListChecks,
  Lock,
  MonitorPlay,
  PanelTop,
  Play,
  Plug,
  Puzzle,
  ScrollText,
  ShieldCheck,
  SquareTerminal,
  type LucideIcon,
} from 'lucide-react'
import { Logo } from '@eyrie/components/Logo'
import { Card } from '@eyrie/components/ui/card'
import { ButtonLink, Command, CopyButton, Eyebrow, ThemeToggle } from './components'
import { Diagram } from './Diagram'

const REPO = 'https://github.com/abrahamalen/eyrie'
const RELEASES = `${REPO}/releases`
const VERSION = __EYRIE_VERSION__

const wrap = 'mx-auto w-full max-w-[1200px] px-4 sm:px-6'

function Section({ id, eyebrow, title, intro, children }: { id: string; eyebrow: string; title: ReactNode; intro: ReactNode; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="border-b py-16 last:border-b-0 sm:py-20">
      <div className={wrap}>
        <div className="mb-9 grid items-end gap-4 md:grid-cols-2 md:gap-10">
          <div>
            <Eyebrow accent>{eyebrow}</Eyebrow>
            <h2 id={`${id}-title`} className="mt-3.5 text-[clamp(28px,3.6vw,44px)] leading-[1.05] font-bold tracking-[-0.035em] text-balance">
              {title}
            </h2>
          </div>
          <p className="text-base text-muted-foreground">{intro}</p>
        </div>
        {children}
      </div>
    </section>
  )
}

function Header() {
  const nav = [
    ['#what', 'What it does'],
    ['#how', 'How it works'],
    ['#security', 'Security'],
    ['#install', 'Install'],
  ]
  return (
    <header className="border-b">
      <div className={`${wrap} flex items-center gap-4 py-4`}>
        <a href="#top" aria-label="Eyrie, top of page" className="rounded-lg no-underline">
          <Logo />
        </a>
        <nav aria-label="Sections" className="mx-auto hidden gap-6 text-sm text-muted-foreground lg:flex">
          {nav.map(([href, label]) => (
            <a key={href} href={href} className="no-underline hover:text-foreground">
              {label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2 lg:ml-0">
          <a href={REPO} className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-[13.5px] font-medium no-underline hover:text-brand">
            GitHub <ArrowUpRight className="size-3.5" aria-hidden />
          </a>
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}

const DEAL = [
  ['Reads what’s already there', 'Your tools’ own config, transcripts and state. No sync, no second copy.'],
  ['Changes through their CLIs', 'claude mcp, claude plugin, codex mcp, gemini mcp. Eyrie never edits their config files directly.'],
  ['Shows the command first', 'Every change previews the exact command. Destructive ones ask again.'],
  ['Logs everything it does', 'An audit trail of every action, with secrets masked.'],
]

function Hero() {
  return (
    <section id="top" className="border-b py-16 sm:py-20" aria-labelledby="hero-title">
      <div className={`${wrap} grid items-center gap-12 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)] lg:gap-14`}>
        <div className="min-w-0">
          <Eyebrow dot>Local · on your machine only</Eyebrow>
          <h1 id="hero-title" className="mt-5 text-[clamp(40px,6.2vw,78px)] leading-[0.98] font-bold tracking-[-0.045em] text-balance">
            Every coding agent on your machine, <span className="serif text-[1.04em]">in one place.</span>
          </h1>
          <p className="mt-6 max-w-[34em] text-lg leading-relaxed text-muted-foreground sm:text-[19px]">
            Eyrie runs your Claude Code, Codex and Gemini CLI sessions, manages their MCP servers, plugins and agent memory, and
            tracks what they cost. It works with the files and CLIs those tools already use, and your data never leaves your machine.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="#install" primary>
              Install Eyrie <ArrowRight className="size-4" aria-hidden />
            </ButtonLink>
            <ButtonLink href="#how">
              See how it works <ArrowDown className="size-4" aria-hidden />
            </ButtonLink>
          </div>
          <p className="mt-6 font-mono text-xs text-muted-foreground">127.0.0.1 only · No accounts · MIT licensed</p>
        </div>
        <Card className="min-w-0 gap-0 px-6 [--card-spacing:--spacing(6)] sm:px-7">
          <div className="flex justify-between border-b pb-4">
            <Eyebrow className="text-[11px]">The deal</Eyebrow>
            <Eyebrow accent className="text-[11px]">01–04</Eyebrow>
          </div>
          <ol className="m-0 list-none p-0">
            {DEAL.map(([h, p], i) => (
              <li key={h} className="grid grid-cols-[30px_minmax(0,1fr)] gap-1 pt-5">
                <span className="pt-0.5 font-mono text-xs text-muted-foreground">0{i + 1}</span>
                <div>
                  <h3 className="text-base font-semibold tracking-[-0.01em]">{h}</h3>
                  <p className="mt-1 text-[14.5px] text-muted-foreground">{p}</p>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </section>
  )
}

function Stats() {
  const stats = [
    ['03', 'Agents: Claude Code, Codex, Gemini CLI'],
    ['03', 'Platforms: macOS, Debian/Ubuntu, Fedora'],
    ['00', 'Accounts or telemetry'],
    [`v${VERSION}`, 'Current release'],
  ]
  return (
    <div className={wrap}>
      <dl className="m-0 grid grid-cols-2 border-b lg:grid-cols-4">
        {stats.map(([v, k], i) => (
          <div key={k} className={`flex flex-col-reverse justify-end py-5 ${i % 2 ? 'border-l pl-4 sm:pl-6' : 'pr-4'} ${i > 1 ? 'border-t lg:border-t-0' : ''} ${i === 2 ? 'lg:border-l lg:pl-6' : ''}`}>
            <dt className="mt-0.5 text-[13px] text-muted-foreground">{k}</dt>
            <dd className="m-0 font-mono text-[22px] tracking-[-0.02em] tabular-nums sm:text-[26px]">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

type Feature = { icon: LucideIcon; title: string; tag: string; body: string; cmd: string }
const FEATURES: Feature[] = [
  {
    icon: MonitorPlay,
    title: 'Sessions',
    tag: 'Manage',
    body: 'Start, resume and stop Claude Code, Codex and Gemini CLI in Eyrie’s own tmux server, and see the ones running in your own terminals. Type into them in the browser, or attach from any terminal.',
    cmd: 'tmux -L eyrie attach -t eyrie-7f3a',
  },
  {
    icon: ChartColumnStacked,
    title: 'Usage and cost',
    tag: 'Read-only',
    body: 'Cost and tokens per day, tool, model and project, built from session transcripts and kept after Claude Code prunes them.',
    cmd: '~/.eyrie/usage.db',
  },
  {
    icon: Plug,
    title: 'MCP servers',
    tag: 'Manage',
    body: 'Claude Code, Codex and Gemini CLI servers, across their user, local and project scopes. Add or remove one; Eyrie shows the exact command first.',
    cmd: 'claude mcp add -s user -t stdio sqlite -- uvx mcp-server-sqlite',
  },
  {
    icon: Puzzle,
    title: 'Plugins',
    tag: 'Manage',
    body: 'Enable or disable Claude Code plugins through Claude Code’s own plugin command.',
    cmd: 'claude plugin disable name@marketplace --json',
  },
  {
    icon: Bot,
    title: 'Agent memory',
    tag: 'Manage',
    body: 'Browse, edit, create and delete what your Claude Code subagents remember. Edits never overwrite an agent’s change made in the meantime; deletes go to a trash folder.',
    cmd: '~/.claude/agent-memory/<agent>/*.md',
  },
  {
    icon: ListChecks,
    title: 'Tasks',
    tag: 'Manage',
    body: 'A personal checklist in a markdown file you choose, edited one line at a time so the rest of the file stays as you wrote it.',
    cmd: 'EYRIE_PATHS__TASKS=~/notes/Tasks.md',
  },
]

function WhatItDoes() {
  return (
    <Section
      id="what"
      eyebrow="01 / What it does"
      title="One place for the tools you already run."
      intro="Each page is a thin layer over something you’d otherwise do by hand: a tmux command, a CLI call, a file on disk. Eyrie shows you the thing it runs."
    >
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, tag, body, cmd }) => (
          <Card key={title} className="min-w-0 gap-3 px-6 [--card-spacing:--spacing(6)]">
            <div className="flex items-center justify-between">
              <span className="grid size-[38px] place-items-center rounded-[10px] border bg-muted text-brand">
                <Icon className="size-[18px]" aria-hidden />
              </span>
              <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">{tag}</span>
            </div>
            <h3 className="text-[19px] font-semibold tracking-[-0.02em]">{title}</h3>
            <p className="flex-1 text-[14.5px] leading-relaxed text-muted-foreground">{body}</p>
            <Command text={cmd} wrap />
          </Card>
        ))}
      </div>
      <Card className="mt-4 min-w-0 gap-6 px-6 [--card-spacing:--spacing(6)] md:flex-row md:items-center">
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          <div className="flex items-center gap-3">
            <span className="grid size-[38px] place-items-center rounded-[10px] border bg-muted text-brand">
              <PanelTop className="size-[18px]" aria-hidden />
            </span>
            <h3 className="text-[19px] font-semibold tracking-[-0.02em]">The top-bar widget</h3>
          </div>
          <p className="max-w-[60ch] text-[14.5px] leading-relaxed text-muted-foreground">
            A small menu-bar (macOS) or top-bar (Linux) app. Its icon changes when something needs you, today’s cost sits next to
            it on macOS, and its panel shows what needs you, live sessions and quick actions. It talks only to your own Eyrie on
            127.0.0.1, and starts at login unless you turn that off.
          </p>
        </div>
        <WidgetSketch />
      </Card>
    </Section>
  )
}

/** A static sketch of the widget's panel (no data, no screenshot). */
function WidgetSketch() {
  const rows = [
    ['bg-chart-1', 'eyrie-7f3a', 'Claude Code · running'],
    ['bg-[var(--series-4)]', 'eyrie-2c91', 'Codex · idle 14 min'],
  ]
  return (
    <div aria-hidden className="w-full shrink-0 rounded-xl border bg-background p-4 md:w-[300px]">
      <div className="flex items-center gap-2 border-b pb-3">
        <span className="flex size-6 items-center justify-center rounded-md bg-primary text-[13px] font-bold tracking-[-0.04em] text-primary-foreground">
          e<span className="text-brand">.</span>
        </span>
        <span className="text-sm font-semibold">Eyrie</span>
        <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="size-1.5 rounded-full bg-[var(--series-4)]" />1 needs you
        </span>
      </div>
      <div className="eyebrow mt-3 text-[10px]">Sessions</div>
      {rows.map(([dot, name, meta]) => (
        <div key={name} className="mt-2 flex items-center gap-2.5">
          <span className={`size-1.5 rounded-full ${dot}`} />
          <span className="min-w-0">
            <span className="block font-mono text-[12.5px]">{name}</span>
            <span className="block text-[11.5px] text-muted-foreground">{meta}</span>
          </span>
        </div>
      ))}
      <div className="mt-3 flex gap-2 border-t pt-3">
        <span className="rounded-md border px-2 py-1 text-[11.5px]">+ Session in…</span>
        <span className="ml-auto rounded-md bg-primary px-2 py-1 text-[11.5px] text-primary-foreground">Open Eyrie</span>
      </div>
    </div>
  )
}

const STEPS: [LucideIcon, string, string, string][] = [
  [Eye, 'Read', 'Eyrie reads Claude Code’s, Codex’s and Gemini CLI’s own config, transcripts and state, and the processes running in your terminals.', 'Files · no copies'],
  [SquareTerminal, 'Preview', 'A change is built as an argument list for the tool’s own CLI and shown to you before it runs.', 'Command · confirm'],
  [Play, 'Run', 'The CLI makes the change. Sessions start in Eyrie’s private tmux server, separate from yours, and keep running if Eyrie restarts.', 'CLI · tmux -L eyrie'],
  [ScrollText, 'Log', 'Every action, terminal connection and edit is written to the audit log, with secrets masked.', '~/.eyrie/audit.jsonl'],
]

function HowItWorks() {
  return (
    <Section
      id="how"
      eyebrow="02 / How it works"
      title="Thin, local, and honest about what it does."
      intro="A small Python service on 127.0.0.1 with a React UI, plus the widget. Your browser and the widget talk only to it; it talks only to your tools."
    >
      <Card className="min-w-0 px-4 [--card-spacing:--spacing(5)] sm:px-8 sm:[--card-spacing:--spacing(8)]">
        <Diagram />
      </Card>
      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <Card className="min-w-0 gap-4 px-6 [--card-spacing:--spacing(7)] sm:px-8">
          <Eyebrow dot>Example · starting a session</Eyebrow>
          <h3 className="text-2xl font-semibold tracking-[-0.025em]">
            You click <span className="serif">New session.</span>
          </h3>
          <p className="text-[14.5px] text-muted-foreground">
            Pick a project. Eyrie shows the exact tmux command, runs it, and records it. The session is yours: attach to it from any
            terminal, and it keeps running if Eyrie stops.
          </p>
          <Command
            text={'tmux -L eyrie new-session -d \\\n  -s eyrie-7f3a -c ~/projects/blog \\\n  claude --session-id 0f3c9a52-…'}
            copy="tmux -L eyrie attach -t eyrie-7f3a"
            wrap={false}
          />
        </Card>
        <Card className="min-w-0 px-6 [--card-spacing:--spacing(7)] sm:px-8">
          <Eyebrow className="mb-2 text-[11px]">What happens</Eyebrow>
          <ol className="m-0 list-none p-0">
            {STEPS.map(([Icon, h, p, t], i) => (
              <li key={h} className="relative grid grid-cols-[36px_minmax(0,1fr)] gap-4 pb-6 last:pb-0">
                {i < STEPS.length - 1 && <span aria-hidden className="absolute top-9 bottom-0 left-[17.5px] w-px bg-border" />}
                <span className="grid size-9 place-items-center rounded-full border bg-muted">
                  <Icon className="size-4" aria-hidden />
                </span>
                <div>
                  <h4 className="text-base font-semibold">{h}</h4>
                  <p className="mt-0.5 text-[14.5px] text-muted-foreground">{p}</p>
                  <div className="mt-1.5 font-mono text-[11.5px] tracking-[0.1em] text-brand uppercase">{t}</div>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
    </Section>
  )
}

const SAFETY: [LucideIcon, string, string][] = [
  [Lock, 'Localhost only', 'Listens on 127.0.0.1 and rejects any Host or Origin that isn’t loopback, so another website or a DNS-rebinding page can’t drive it.'],
  [KeyRound, 'A token for every change', 'Writes need the per-install token in ~/.eyrie/token (mode 600). The UI gets it from a same-origin endpoint.'],
  [SquareTerminal, 'No “run anything”', 'A fixed list of actions. CLIs are called with argument lists, never through a shell, and their config files are never edited directly.'],
  [FileCheck, 'Never overwrites your edits', 'Every write is checked against what you last saw (etags) and confined to its folder.'],
  [ShieldCheck, 'Can’t be framed', "Pages send X-Frame-Options: DENY and frame-ancestors 'none', so no other site can wrap Eyrie and trick you into a click."],
  [ScrollText, 'Audited, secrets masked', 'Actions, terminal connections, memory and task edits are logged to ~/.eyrie/audit.jsonl, with secrets masked.'],
]

function Security() {
  return (
    <Section
      id="security"
      eyebrow="03 / Security"
      title="It can run commands as you, so it only listens to you."
      intro="Built for one person on one machine. The defaults assume another website might try to drive it."
    >
      <ul className="m-0 grid list-none p-0 md:grid-cols-2">
        {SAFETY.map(([Icon, h, p], i) => (
          <li
            key={h}
            className={`grid grid-cols-[36px_minmax(0,1fr)] gap-2 border-t py-5 ${i % 2 ? 'md:border-l md:pl-8' : 'md:pr-8'}`}
          >
            <Icon className="mt-0.5 size-[18px] text-brand" aria-hidden />
            <div>
              <h3 className="text-base font-semibold">{h}</h3>
              <p className="mt-0.5 text-[14.5px] text-muted-foreground">{p}</p>
            </div>
          </li>
        ))}
      </ul>
    </Section>
  )
}

const INSTALL_SH = 'curl -fsSL https://alenabraham.me/eyrie/install.sh | sh'
const BREW = [
  ['brew install abrahamalen/eyrie/eyrie', 'App + widget (cask, macOS)'],
  ['brew install abrahamalen/eyrie/eyrie-server', 'Server only (formula, macOS + Linux)'],
]

function Install() {
  return (
    <Section
      id="install"
      eyebrow="04 / Install"
      title="A couple of minutes, then it’s in your menu bar."
      intro={
        <>
          Needs tmux and whichever of Claude Code, Codex and Gemini CLI you use. Runs on macOS, Debian/Ubuntu and Fedora; Windows
          is planned. Your data stays in <span className="font-mono text-[14px]">~/.eyrie</span> and your tools’ own config.
        </>
      }
    >
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="min-w-0 gap-3 px-6 [--card-spacing:--spacing(6)]">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-[17px] font-semibold">One line</h3>
            <span className="eyebrow text-[10.5px]">macOS · Linux</span>
          </div>
          <p className="text-[14.5px] text-muted-foreground">
            Detects your system, downloads the matching release, checks it against SHA256SUMS, installs it and starts the background
            service.
          </p>
          <Command text={INSTALL_SH} wrap />
          <p className="text-[13px] text-muted-foreground">
            Add <span className="font-mono">--server-only</span> on a machine without a desktop.{' '}
            <a href="https://alenabraham.me/eyrie/install.sh" className="text-foreground underline underline-offset-2 hover:text-brand">
              Read the script first
            </a>
            .
          </p>
        </Card>
        <Card className="min-w-0 gap-3 px-6 [--card-spacing:--spacing(6)]">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-[17px] font-semibold">Homebrew</h3>
            <span className="eyebrow text-[10.5px]">macOS · Linux</span>
          </div>
          {BREW.map(([cmd, what]) => (
            <div key={cmd} className="flex min-w-0 flex-col gap-1.5">
              <p className="text-[14.5px] text-muted-foreground">{what}</p>
              <Command text={cmd} wrap />
            </div>
          ))}
        </Card>
        <Card className="min-w-0 gap-3 px-6 [--card-spacing:--spacing(6)]">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-[17px] font-semibold">Download</h3>
            <span className="eyebrow text-[10.5px]">GitHub releases</span>
          </div>
          <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[14.5px] text-muted-foreground">
            <li>
              <span className="font-medium text-foreground">macOS</span>: a .dmg for Apple silicon or Intel
            </li>
            <li>
              <span className="font-medium text-foreground">Debian / Ubuntu</span>: a .deb, plus an AppImage
            </li>
            <li>
              <span className="font-medium text-foreground">Fedora</span>: an .rpm
            </li>
            <li>
              <span className="font-medium text-foreground">Server only</span>: a tarball, for machines without a desktop
            </li>
          </ul>
          <p className="rounded-lg border bg-tint px-3.5 py-2.5 text-[13px] text-muted-foreground">
            The macOS app isn’t signed yet. The first time you open a .dmg you downloaded in a browser, right-click Eyrie and choose{' '}
            <span className="font-medium text-foreground">Open</span>.
          </p>
          <div className="mt-auto pt-1">
            <ButtonLink href={RELEASES}>
              All releases <ArrowUpRight className="size-4" aria-hidden />
            </ButtonLink>
          </div>
        </Card>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2 text-[13.5px] text-muted-foreground">
        <span>Or from source:</span>
        <code className="cmd px-2.5 py-1 text-[12px]">make install</code>
        <CopyButton text={`git clone ${REPO}.git && cd eyrie && make install`} label="Copy clone + install" />
      </div>
    </Section>
  )
}

function Source() {
  return (
    <Section
      id="source"
      eyebrow="05 / Source"
      title={
        <>
          Built in the open, <span className="serif">read every line.</span>
        </>
      }
      intro="Eyrie is a personal project, MIT licensed. The code, the design docs and every release, with its checksums, are on GitHub."
    >
      <div className="flex flex-wrap gap-3">
        <ButtonLink href={REPO} primary>
          abrahamalen/eyrie <ArrowUpRight className="size-4" aria-hidden />
        </ButtonLink>
        <ButtonLink href={RELEASES}>
          Releases <ArrowUpRight className="size-4" aria-hidden />
        </ButtonLink>
        <ButtonLink href={`${REPO}/issues`}>
          Issues <ArrowUpRight className="size-4" aria-hidden />
        </ButtonLink>
      </div>
    </Section>
  )
}

function Footer() {
  return (
    <footer className="border-t py-7">
      <div className={`${wrap} flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-muted-foreground`}>
        <span>
          Eyrie · a personal project by{' '}
          <a href="https://alenabraham.me/" className="text-foreground hover:text-brand">
            Alen Abraham
          </a>
        </span>
        <a href={REPO} className="hover:text-foreground">
          GitHub
        </a>
        <a href={RELEASES} className="hover:text-foreground">
          Releases
        </a>
        <a href={`${REPO}/blob/main/LICENSE`} className="hover:text-foreground">
          MIT License
        </a>
        <span className="font-mono sm:ml-auto">v{VERSION}</span>
      </div>
    </footer>
  )
}

export function App() {
  return (
    <div className="min-h-svh overflow-x-clip">
      <a
        href="#what"
        className="sr-only rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50"
      >
        Skip to content
      </a>
      <Header />
      <main>
        <Hero />
        <Stats />
        <WhatItDoes />
        <HowItWorks />
        <Security />
        <Install />
        <Source />
      </main>
      <Footer />
    </div>
  )
}
