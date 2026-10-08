/**
 * Author: Joonyoung Ki
 *
 * Helpers for presenting match scores (percentage clamping and colour thresholds).
 */
/** Pick the gauge colour token for a percentage: >= 80 good, >= 60 brand, otherwise warning. */
export function scoreColor(pct: number): string {
  if (pct >= 80) return 'var(--ok)'
  if (pct >= 60) return 'var(--brand-text)'
  return 'var(--warn)'
}

/** Convert a 0-1 similarity score to a percentage clamped to the 0-100 range. */
export function clampPct(score: number): number {
  return Math.max(0, Math.min(100, score * 100))
}
