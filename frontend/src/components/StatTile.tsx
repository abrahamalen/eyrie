export function StatTile({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="rounded-xl bg-card px-4 py-3 text-card-foreground ring-1 ring-foreground/10">
      <div className="text-2xl font-semibold tabular-nums tracking-tight">{value}</div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  )
}
