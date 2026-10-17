export function StatTile({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="rounded-xl bg-card px-5 py-4 text-card-foreground ring-1 ring-border">
      <div className="font-mono text-[26px] leading-tight tracking-[-0.02em] tabular-nums">{value}</div>
      <div className="mt-1 text-[13px] text-muted-foreground">{label}</div>
    </div>
  )
}
