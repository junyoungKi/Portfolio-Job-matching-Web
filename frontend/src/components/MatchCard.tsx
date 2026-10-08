/**
 * Author: Joonyoung Ki
 *
 * Card for a single matched job.
 *
 * Shows rank, title, company, location, salary, the AI summary, required skills (highlighting those the
 * user selected as filters), a score gauge and an expandable detailed analysis in the current language.
 */
import { Banknote, Building2, Check, ChevronDown, MapPin } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useId } from 'react'
import type { Translation } from '../lib/i18n'
import { clampPct } from '../lib/score'
import { parseSkills } from '../lib/skills'
import type { JobMatch, Lang } from '../types'
import { ScoreGauge } from './ScoreGauge'

/** Props of `MatchCard`. */
interface Props {
  t: Translation
  lang: Lang
  job: JobMatch
  rank: number
  index: number
  open: boolean
  selectedSkills: string[]
  onToggle: () => void
}

/** One match result with an accessible show/hide detail section. */
export function MatchCard({ t, lang, job, rank, index, open, selectedSkills, onToggle }: Props) {
  const detailId = useId()
  const summary = lang === 'ko' ? job.summary_ko : job.summary_en
  const analysis = lang === 'ko' ? job.analysis_ko : job.analysis_en
  const pct = clampPct(job.match_score)
  const skills = parseSkills(job.skills)
  const wanted = new Set(selectedSkills.map((s) => s.toLowerCase()))
  const hits = skills.filter((s) => wanted.has(s.toLowerCase()))
  const rest = skills.filter((s) => !wanted.has(s.toLowerCase()))
  const ordered = [...hits, ...rest]
  const salary = job.salary && job.salary.trim() !== '' && job.salary !== 'None' ? job.salary : t.salaryUnknown

  return (
    <article
      className="animate-fade-up group overflow-hidden rounded-2xl border border-line bg-surface shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-brand/50 hover:shadow-lg"
      style={{ '--i': Math.min(index, 8) } as CSSProperties}
    >
      <div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-start sm:gap-6 sm:p-6">
        <div className="flex min-w-0 flex-1 gap-4">
          <span
            className="hidden size-12 shrink-0 place-items-center rounded-xl bg-brand-soft text-lg font-bold text-brand-text sm:grid"
            aria-hidden="true"
          >
            {(job.company.trim()[0] ?? '?').toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-xs font-semibold text-subtle">
              <span className="rounded-md bg-surface-2 px-1.5 py-0.5 tabular text-muted">{t.rank(rank)}</span>
            </div>
            <h3 className="mt-1.5 text-lg font-bold leading-snug tracking-tight text-fg sm:text-xl">{job.title}</h3>
            <ul className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-muted">
              <li className="inline-flex items-center gap-1.5">
                <Building2 className="size-4 text-subtle" aria-hidden="true" />
                <span className="font-medium text-fg">{job.company}</span>
              </li>
              <li className="inline-flex items-center gap-1.5">
                <MapPin className="size-4 text-subtle" aria-hidden="true" />
                {job.location}
              </li>
              <li className="inline-flex items-center gap-1.5">
                <Banknote className="size-4 text-subtle" aria-hidden="true" />
                <span className="font-medium text-ok">{salary}</span>
              </li>
            </ul>

            <p className="mt-4 rounded-lg bg-surface-2 px-3.5 py-3 text-sm leading-relaxed text-muted">
              {summary || t.noSummary}
            </p>

            <div className="mt-4">
              <p className="mb-2 text-xs font-semibold text-subtle">{t.skillsTitle}</p>
              {ordered.length > 0 ? (
                <ul className="flex flex-wrap gap-1.5">
                  {ordered.map((s) => {
                    const hit = wanted.has(s.toLowerCase())
                    return (
                      <li
                        key={s}
                        title={hit ? t.skillHit : undefined}
                        className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors ${
                          hit
                            ? 'border-ok/40 bg-ok-soft text-ok'
                            : 'border-line bg-surface text-muted group-hover:border-line-strong'
                        }`}
                      >
                        {hit && <Check className="size-3" strokeWidth={3} aria-hidden="true" />}
                        {s}
                        {hit && <span className="sr-only"> — {t.skillHit}</span>}
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <p className="text-sm text-subtle">{t.noSkills}</p>
              )}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-4 border-t border-line pt-4 sm:flex-col sm:border-t-0 sm:pt-0">
          <ScoreGauge pct={pct} size={92} stroke={8} label={t.matchLabel} ariaLabel={t.scoreAria(Math.round(pct))} />
          <p className="tabular text-sm text-muted sm:hidden">
            {t.matchLabel} <strong className="font-bold text-fg">{pct.toFixed(1)}%</strong>
          </p>
        </div>
      </div>

      <div
        className={`grid transition-[grid-template-rows] duration-300 ease-out ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
      >
        <div className="overflow-hidden">
          <div id={detailId} className="border-t border-line bg-surface-2/60 px-5 py-5 sm:px-6" inert={!open}>
            <h4 className="mb-2 text-xs font-semibold text-subtle">{t.detailTitle}</h4>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg">{analysis || t.noSummary}</p>
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={detailId}
        className="flex w-full items-center justify-center gap-1.5 border-t border-line py-3 text-sm font-semibold text-brand-text transition-colors hover:bg-brand-soft"
      >
        {open ? t.hideDetail : t.showDetail}
        <ChevronDown className={`size-4 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
    </article>
  )
}
