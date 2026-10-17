/** Eyrie's mark: an ink tile with "e." where the dot carries the brand colour. */
export function Logo({ tagline = true }: { tagline?: boolean }) {
  return (
    <span className="inline-flex items-center gap-3">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary text-[15px] font-bold tracking-[-0.04em] text-primary-foreground">
        e<span className="text-brand">.</span>
      </span>
      <span className="text-[17px] font-semibold tracking-[-0.02em] group-data-[collapsible=icon]:hidden">Eyrie</span>
      {tagline && (
        <span className="eyebrow hidden border-l pl-3 text-[10.5px] md:inline group-data-[collapsible=icon]:hidden">
          Agent control plane
        </span>
      )}
    </span>
  )
}
