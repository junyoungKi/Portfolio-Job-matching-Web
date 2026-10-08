/**
 * Author: Joonyoung Ki
 *
 * Results panel.
 *
 * Renders the idle, loading (skeleton), error, empty and success states, and for successful results
 * offers sorting by match score or by salary.
 */
import { ArrowUpDown, RotateCw } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Translation } from '../lib/i18n'
import { jobKey } from '../lib/jobKey'
import { hasSalaryData, parseSalary } from '../lib/salary'
import type { JobMatch, Lang, ResultsState } from '../types'
import { ErrorIllustration, IdleIllustration, NoResultIllustration } from './Illustrations'
import { MatchCard } from './MatchCard'

/** Props of `MatchList`. */
interface Props {
  t: Translation
  lang: Lang
  state: ResultsState
  openKeys: Set<string>
  selectedSkills: string[]
  onToggle: (key: string) => void
  onRetry: () => void
  canRetry: boolean
}

/** Available sort orders for the results. */
type SortKey = 'score' | 'salary'

/** Centered placeholder with an illustration, title, optional body text and optional action button. */
function EmptyState({
  illustration,
  title,
  body,
  action,
}: {
  illustration: ReactNode
  title: string
  body: string
  action?: ReactNode
}) {
  return (
    <div className="animate-fade-up flex flex-col items-center rounded-2xl border border-dashed border-line-strong bg-surface px-6 py-12 text-center">
      <div className="w-48 sm:w-56">{illustration}</div>
      <h3 className="mt-4 text-lg font-bold text-fg">{title}</h3>
      {body && <p className="mt-1.5 max-w-md text-sm leading-relaxed text-muted">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/** Shimmering placeholder cards shown while results are loading. */
function Skeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-2xl border border-line bg-surface p-6 shadow-sm">
          <div className="flex gap-5">
            <div className="skeleton hidden size-12 rounded-xl sm:block" />
            <div className="flex-1 space-y-3">
              <div className="skeleton h-5 w-24 rounded-md" />
              <div className="skeleton h-6 w-2/3 rounded-md" />
              <div className="skeleton h-4 w-1/2 rounded-md" />
              <div className="skeleton h-16 w-full rounded-lg" />
              <div className="flex gap-2">
                <div className="skeleton h-6 w-16 rounded-full" />
                <div className="skeleton h-6 w-20 rounded-full" />
                <div className="skeleton h-6 w-14 rounded-full" />
              </div>
            </div>
            <div className="skeleton hidden size-[92px] rounded-full sm:block" />
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Return a sorted copy of the matches.
 *
 * Salary sorting puts jobs without a parsable salary last; ties fall back to the match score.
 */
function sortMatches(matches: JobMatch[], sort: SortKey): JobMatch[] {
  const copy = [...matches]
  if (sort === 'salary') {
    copy.sort((a, b) => {
      const sa = parseSalary(a.salary)
      const sb = parseSalary(b.salary)
      if (sa === null && sb === null) return b.match_score - a.match_score
      if (sa === null) return 1
      if (sb === null) return -1
      return sb - sa || b.match_score - a.match_score
    })
  } else {
    copy.sort((a, b) => b.match_score - a.match_score)
  }
  return copy
}

/** Results section whose content depends on the request state (`idle`, `loading`, `error`, `success`). */
export function MatchList({ t, lang, state, openKeys, selectedSkills, onToggle, onRetry, canRetry }: Props) {
  const [sortPref, setSortPref] = useState<SortKey>('score')
  const matches = state.status === 'success' ? state.matches : null
  const salaryAvailable = useMemo(() => (matches ? hasSalaryData(matches) : false), [matches])
  const sort: SortKey = sortPref === 'salary' && salaryAvailable ? 'salary' : 'score'
  const sorted = useMemo(() => (matches ? sortMatches(matches, sort) : []), [matches, sort])

  return (
    <section aria-labelledby="results-heading" aria-busy={state.status === 'loading'}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 id="results-heading" className="text-lg font-bold tracking-tight text-fg sm:text-xl">
            {t.resultTitle}
          </h2>
          {matches && matches.length > 0 && (
            <span className="tabular rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-semibold text-brand-text">
              {t.resultCount(matches.length)}
            </span>
          )}
        </div>
        {matches && matches.length > 1 && (
          <label className="flex items-center gap-2 text-sm text-muted">
            <ArrowUpDown className="size-4 text-subtle" aria-hidden="true" />
            <span>{t.sortLabel}</span>
            <select
              value={sort}
              onChange={(e) => setSortPref(e.target.value as SortKey)}
              className="h-9 rounded-lg border border-line-strong bg-surface px-2.5 text-sm font-medium text-fg focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand-soft"
            >
              <option value="score">{t.sortScore}</option>
              <option value="salary" disabled={!salaryAvailable}>
                {salaryAvailable ? t.sortSalary : t.sortSalaryDisabled}
              </option>
            </select>
          </label>
        )}
      </div>

      <div aria-live="polite">
        {state.status === 'idle' && (
          <EmptyState
            illustration={<IdleIllustration className="h-auto w-full" />}
            title={t.emptyIdleTitle}
            body={t.emptyIdleBody}
          />
        )}
        {state.status === 'loading' && <Skeleton />}
        {state.status === 'error' && (
          <div role="alert">
            <EmptyState
              illustration={<ErrorIllustration className="h-auto w-full" />}
              title={t.errorTitle}
              body={state.message}
              action={
                canRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-brand-on transition-colors hover:bg-brand-hover"
                  >
                    <RotateCw className="size-4" aria-hidden="true" />
                    {t.retry}
                  </button>
                )
              }
            />
          </div>
        )}
        {state.status === 'success' &&
          (state.matches.length === 0 ? (
            <EmptyState
              illustration={<NoResultIllustration className="h-auto w-full" />}
              title={t.emptyResultTitle}
              body={t.emptyResultBody}
            />
          ) : (
            <div className="space-y-4">
              {sorted.map((job, idx) => {
                const key = jobKey(job, state.matches.indexOf(job))
                return (
                  <MatchCard
                    key={key}
                    t={t}
                    lang={lang}
                    job={job}
                    rank={idx + 1}
                    index={idx}
                    open={openKeys.has(key)}
                    selectedSkills={selectedSkills}
                    onToggle={() => onToggle(key)}
                  />
                )
              })}
            </div>
          ))}
      </div>
    </section>
  )
}
