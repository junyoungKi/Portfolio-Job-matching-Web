export function scoreColor(pct: number): string {
  if (pct >= 80) return 'var(--ok)'
  if (pct >= 60) return 'var(--brand-text)'
  return 'var(--warn)'
}

export function clampPct(score: number): number {
  return Math.max(0, Math.min(100, score * 100))
}
