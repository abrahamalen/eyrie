export type Metric = 'cost' | 'tokens'

// Colour follows the model, never its rank, so a range change never repaints a series.
// Slots are in the palette's validated order; anything else folds into "Other".
const MODEL_SLOTS: Record<string, number> = {
  'claude-opus-5-5': 1,
  'claude-sonnet-5-5': 2,
  'claude-haiku-5-5': 3,
  'claude-opus-5': 4,
  'claude-sonnet-5': 5,
  'claude-opus-4-7': 6,
  'claude-sonnet-4-6': 7,
}
export const OTHER = 'Other'

export function seriesOf(model: string): string {
  return model in MODEL_SLOTS ? model : OTHER
}

export function seriesColor(series: string): string {
  return `var(--series-${MODEL_SLOTS[series] ?? 8})`
}

export function seriesOrder(models: string[]): string[] {
  const present = new Set(models.map(seriesOf))
  return [...Object.keys(MODEL_SLOTS), OTHER].filter((s) => present.has(s))
}
