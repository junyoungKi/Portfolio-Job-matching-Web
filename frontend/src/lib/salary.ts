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

/**
 * Sortable annual salary for a job. Prefers the structured values from the API
 * (USD-approximated annual max, then annual max) and only falls back to guessing
 * from the free-text `salary` field when no structured value exists.
 */
export function jobSalaryValue(job: JobMatch): number | null {
  const structured = job.salary_annual_max_usd_approx ?? job.salary_annual_max ?? job.salary_annual_min_usd_approx ?? job.salary_annual_min
  if (typeof structured === 'number' && structured > 0) return structured
  return parseSalary(job.salary)
}

const PERIOD_SUFFIX: Record<string, string> = {
  hourly: '/hr',
  daily: '/day',
  weekly: '/wk',
  biweekly: '/2wk',
  monthly: '/mo',
  yearly: '/yr',
}

/**
 * Human-readable salary from structured fields (e.g. "USD 120,000 - 150,000 /yr"),
 * or null when the job has no structured salary amounts.
 */
export function formatStructuredSalary(job: JobMatch): string | null {
  const lo = job.salary_min ?? null
  const hi = job.salary_max ?? null
  if (lo === null && hi === null) return null
  const fmt = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 })
  const amount = lo !== null && hi !== null && lo !== hi ? `${fmt(lo)} - ${fmt(hi)}` : lo === null ? `up to ${fmt(hi as number)}` : hi === null ? `from ${fmt(lo)}` : fmt(lo)
  const suffix = job.salary_period ? (PERIOD_SUFFIX[job.salary_period] ?? '') : ''
  return [job.salary_currency, amount, suffix].filter(Boolean).join(' ')
}

export function hasSalaryData(jobs: JobMatch[]): boolean {
  return jobs.some((j) => jobSalaryValue(j) !== null)
}
