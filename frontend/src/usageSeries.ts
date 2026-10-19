import type { UsageReport } from '@/api/types'

export type Metric = 'cost' | 'tokens'

// The daily chart stacks by tool; models are in the table below it. Colour follows the tool,
// never its rank, so a range change never repaints a series. Slots are in the palette's
// validated order; an unknown tool takes the last slot.
const TOOL_SLOTS: Record<string, number> = { claude: 1, codex: 2, gemini: 3 }

export function seriesColor(tool: string): string {
  return `var(--series-${TOOL_SLOTS[tool] ?? 8})`
}

export function seriesOrder(tools: string[]): string[] {
  return [...new Set(tools)].sort((a, b) => (TOOL_SLOTS[a] ?? 99) - (TOOL_SLOTS[b] ?? 99))
}

/** model → the tool it was used through, from the report's own model rows. */
export function toolOfModel(report: UsageReport): (model: string) => string {
  const map = new Map(report.by_model.map((m) => [m.model, m.tool]))
  return (model) => map.get(model) ?? 'other'
}
