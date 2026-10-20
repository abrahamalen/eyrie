/* "How it works" as a diagram: you talk to Eyrie on loopback; Eyrie reads your tools' files,
   changes things through their CLIs, runs sessions in its own tmux server, and logs to ~/.eyrie.
   Two layouts (wide and tall) so the text stays readable on a phone. Colours are the app's
   tokens via Tailwind fill/stroke classes, so it follows light and dark. */

const LABEL = 'Diagram: your browser and the top-bar widget talk to Eyrie over 127.0.0.1 with a token. Eyrie checks the origin and token, runs only fixed actions as argument lists, reads your tools’ files (~/.claude, ~/.codex, ~/.gemini), runs their CLIs, starts sessions in its own tmux server, and writes an audit log to ~/.eyrie.'

const CHECKS = ['Loopback + Origin check', 'Token on every change', 'Fixed actions, argv, no shell', 'Audit log, secrets masked']

function Box({ x, y, w, h, title, sub, accent }: { x: number; y: number; w: number; h: number; title: string; sub?: string; accent?: boolean }) {
  const cy = y + h / 2
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={12} className={accent ? 'fill-card stroke-brand' : 'fill-card stroke-border'} strokeWidth={1.2} />
      <text x={x + 16} y={sub ? cy - 4 : cy + 5} className="fill-foreground text-[15px] font-semibold">
        {title}
      </text>
      {sub && (
        <text x={x + 16} y={cy + 15} className="fill-muted-foreground font-mono text-[11.5px]">
          {sub}
        </text>
      )}
    </g>
  )
}

function Arrow({ d, id }: { d: string; id: string }) {
  return <path d={d} className="fill-none stroke-muted-foreground" strokeWidth={1.3} markerEnd={`url(#${id})`} />
}

function Marker({ id }: { id: string }) {
  return (
    <marker id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M0 0 10 5 0 10z" className="fill-muted-foreground" />
    </marker>
  )
}

function Caption({ x, y, children, anchor = 'start' }: { x: number; y: number; children: string; anchor?: 'start' | 'middle' | 'end' }) {
  return (
    <text x={x} y={y} textAnchor={anchor} className="fill-muted-foreground font-mono text-[10.5px] tracking-[0.14em] uppercase">
      {children}
    </text>
  )
}

function Mark({ x, y }: { x: number; y: number }) {
  return (
    <g>
      <rect x={x} y={y} width={28} height={28} rx={7} className="fill-primary" />
      <text x={x + 12.5} y={y + 19.5} textAnchor="middle" className="fill-primary-foreground text-[16px] font-bold">
        e
      </text>
      <circle cx={x + 21} cy={y + 18.5} r={2.2} className="fill-brand" />
    </g>
  )
}

function Checks({ x, y, gap }: { x: number; y: number; gap: number }) {
  return (
    <>
      {CHECKS.map((c, i) => (
        <g key={c}>
          <circle cx={x + 4} cy={y + i * gap - 4} r={3} className="fill-brand" />
          <text x={x + 16} y={y + i * gap} className="fill-foreground text-[13.5px]">
            {c}
          </text>
        </g>
      ))}
    </>
  )
}

function Wide() {
  return (
    <svg viewBox="0 0 960 380" className="hidden h-auto w-full md:block" role="img" aria-label={LABEL}>
      <defs>
        <Marker id="arr-w" />
      </defs>
      <Caption x={20} y={28}>You</Caption>
      <Caption x={320} y={28}>Eyrie · 127.0.0.1 only</Caption>
      <Caption x={720} y={28}>Your tools</Caption>

      <Box x={20} y={70} w={210} h={72} title="Browser" sub="the Eyrie UI" />
      <Box x={20} y={190} w={210} h={72} title="Top-bar widget" sub="menu bar · top bar" />

      <rect x={320} y={50} width={300} height={232} rx={14} className="fill-card stroke-brand" strokeWidth={1.4} />
      <Mark x={344} y={70} />
      <text x={384} y={90} className="fill-foreground text-[18px] font-semibold tracking-[-0.02em]">
        Eyrie
      </text>
      <Checks x={346} y={140} gap={36} />

      <Box x={320} y={314} w={300} h={58} title="~/.eyrie" sub="audit.jsonl · usage.db · token" />

      <Box x={720} y={40} w={220} h={72} title="Their files" sub="~/.claude ~/.codex ~/.gemini" />
      <Box x={720} y={140} w={220} h={72} title="Their CLIs" sub="claude · codex · gemini" />
      <Box x={720} y={240} w={220} h={72} title="Sessions" sub="tmux -L eyrie" />

      <Arrow d="M230 106H318" id="arr-w" />
      <Arrow d="M230 226H318" id="arr-w" />
      <Caption x={274} y={98} anchor="middle">token</Caption>
      <Caption x={274} y={218} anchor="middle">token</Caption>

      <Arrow d="M620 76H718" id="arr-w" />
      <Arrow d="M620 176H718" id="arr-w" />
      <Arrow d="M620 276H718" id="arr-w" />
      <Caption x={669} y={68} anchor="middle">reads</Caption>
      <Caption x={669} y={168} anchor="middle">runs</Caption>
      <Caption x={669} y={268} anchor="middle">starts</Caption>

      <Arrow d="M470 282V312" id="arr-w" />
      <Caption x={480} y={302}>logs</Caption>
    </svg>
  )
}

function Tall() {
  return (
    <svg viewBox="0 0 340 600" className="h-auto w-full md:hidden" role="img" aria-label={LABEL}>
      <defs>
        <Marker id="arr-t" />
      </defs>
      <Caption x={0} y={14}>You</Caption>
      <Box x={0} y={26} w={162} h={56} title="Browser" />
      <Box x={178} y={26} w={162} h={56} title="Top-bar widget" />
      <Arrow d="M81 82V122" id="arr-t" />
      <Arrow d="M259 82V122" id="arr-t" />
      <Caption x={170} y={106} anchor="middle">token</Caption>

      <rect x={0.7} y={124} width={338.6} height={200} rx={14} className="fill-card stroke-brand" strokeWidth={1.4} />
      <Mark x={18} y={142} />
      <text x={58} y={162} className="fill-foreground text-[18px] font-semibold tracking-[-0.02em]">
        Eyrie
      </text>
      <text x={322} y={161} textAnchor="end" className="fill-muted-foreground font-mono text-[11px]">
        127.0.0.1
      </text>
      <Checks x={20} y={206} gap={32} />

      <Arrow d="M170 324V362" id="arr-t" />
      <Caption x={160} y={348} anchor="end">reads · runs</Caption>
      <Caption x={180} y={348}>starts · logs</Caption>

      <Box x={0} y={366} w={340} h={50} title="Their files" sub="" />
      <text x={324} y={396} textAnchor="end" className="fill-muted-foreground font-mono text-[11px]">
        ~/.claude ~/.codex ~/.gemini
      </text>
      <Box x={0} y={424} w={340} h={50} title="Their CLIs" />
      <text x={324} y={454} textAnchor="end" className="fill-muted-foreground font-mono text-[11px]">
        claude · codex · gemini
      </text>
      <Box x={0} y={482} w={340} h={50} title="Sessions" />
      <text x={324} y={512} textAnchor="end" className="fill-muted-foreground font-mono text-[11px]">
        tmux -L eyrie
      </text>
      <Box x={0} y={540} w={340} h={50} title="~/.eyrie" />
      <text x={324} y={570} textAnchor="end" className="fill-muted-foreground font-mono text-[11px]">
        audit.jsonl · usage.db
      </text>
    </svg>
  )
}

export function Diagram() {
  return (
    <figure className="m-0">
      <Wide />
      <Tall />
    </figure>
  )
}
