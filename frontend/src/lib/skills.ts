/**
 * Author: Joonyoung Ki
 *
 * Helper for parsing the comma-separated skills string returned by the API.
 */
/**
 * Split the comma-separated `skills` string into trimmed, case-insensitively de-duplicated names.
 *
 * Empty entries and the literal 'none' are dropped; the first spelling of each skill is kept.
 */
export function parseSkills(raw: string | null | undefined): string[] {
  if (!raw) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const part of raw.split(',')) {
    const s = part.trim()
    if (!s || s.toLowerCase() === 'none') continue
    const key = s.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(s)
  }
  return out
}
