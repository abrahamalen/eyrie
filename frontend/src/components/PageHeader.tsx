import type { ReactNode } from 'react'

/** Every page opens the same way: a mono eyebrow, a tight title, one line of context. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
      <div className="min-w-0 flex-1">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="mt-2 text-[2rem] leading-[1.05] font-bold tracking-[-0.035em] text-balance">{title}</h1>
        {description && <p className="mt-2 max-w-[62ch] text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
