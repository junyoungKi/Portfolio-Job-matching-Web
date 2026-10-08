import type { JobMatch } from '../types'

/**
 * Best-effort numeric value (upper bound of a range, annualised) parsed from the free-text
 * `salary` field. Returns null for values such as "Competitive Salary" so they can be sorted last.
 */
export function parseSalary(raw: string | null | undefined): number | null {
  if (!raw) return null
  const text = raw.toLowerCase()
  const matches = [...text.matchAll(/(\d[\d,]*(?:\.\d+)?)\s*(k|m)?/g)]
  const values = matches
    .map((m) => {
      const n = parseFloat(m[1].replace(/,/g, ''))
      if (Number.isNaN(n)) return null
      if (m[2] === 'k') return n * 1_000
      if (m[2] === 'm') return n * 1_000_000
      return n
    })
    .filter((n): n is number => n !== null && n > 0)
  if (values.length === 0) return null
  let max = Math.max(...values)
  if (/\b(hr|hour|hourly)\b|\/h\b/.test(text)) max *= 2080
  else if (/\b(month|monthly|mo)\b/.test(text)) max *= 12
  return max
}

export function hasSalaryData(jobs: JobMatch[]): boolean {
  return jobs.some((j) => parseSalary(j.salary) !== null)
}
