import { useId } from 'react'
import type { Translation } from '../lib/i18n'
import { parseSkills } from '../lib/skills'
import type { JobMatch, Lang } from '../types'

interface Props {
  t: Translation
  lang: Lang
  job: JobMatch
  open: boolean
  selectedSkills: string[]
  onToggle: () => void
}

function scoreTone(pct: number): string {
  if (pct >= 80) return 'text-emerald-400'
  if (pct >= 60) return 'text-blue-400'
  return 'text-amber-400'
}

export function MatchCard({ t, lang, job, open, selectedSkills, onToggle }: Props) {
  const detailId = useId()
  const summary = lang === 'ko' ? job.summary_ko : job.summary_en
  const analysis = lang === 'ko' ? job.analysis_ko : job.analysis_en
  const pct = Math.max(0, Math.min(100, job.match_score * 100))
  const skills = parseSkills(job.skills)
  const wanted = new Set(selectedSkills.map((s) => s.toLowerCase()))

  return (
    <article className="overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/70 transition-colors hover:border-blue-500/50">
      <div className="flex flex-col gap-5 p-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-md bg-blue-500/10 px-2 py-1 font-bold uppercase tracking-wide text-blue-400">{job.company}</span>
            <span className="inline-flex items-center gap-1 font-medium text-slate-400">
              <svg viewBox="0 0 24 24" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z" />
                <circle cx="12" cy="10" r="2.5" />
              </svg>
              {job.location}
            </span>
            <span className="font-mono font-semibold text-emerald-400">{job.salary}</span>
          </div>
          <h3 className="text-xl font-extrabold leading-tight text-white">{job.title}</h3>
          <p className="mt-3 border-l-2 border-blue-500 pl-3 text-sm italic leading-relaxed text-slate-300">
            {summary || t.noSummary}
          </p>
          {skills.length > 0 && (
            <div className="mt-4">
              <span className="sr-only">{t.matchedSkills}</span>
              <ul className="flex flex-wrap gap-1.5">
                {skills.map((s) => {
                  const hit = wanted.has(s.toLowerCase())
                  return (
                    <li
                      key={s}
                      className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${
                        hit
                          ? 'border-emerald-500/50 bg-emerald-500/15 text-emerald-300'
                          : 'border-slate-700 bg-slate-800/60 text-slate-400'
                      }`}
                    >
                      {s}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-3 sm:w-28 sm:flex-col sm:items-end sm:gap-2">
          <div className={`text-4xl font-extrabold tabular-nums tracking-tight ${scoreTone(pct)}`}>
            {pct.toFixed(1)}
            <span className="text-xl">%</span>
          </div>
          <div className="text-[11px] font-bold uppercase tracking-widest text-slate-500">{t.matchLabel}</div>
          <div
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800 sm:w-full sm:flex-none"
            role="progressbar"
            aria-valuenow={Math.round(pct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t.matchLabel}
          >
            <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500" style={{ width: `${pct}%` }} />
          </div>
        </div>
      </div>

      {open && (
        <div id={detailId} className="border-t border-slate-800 bg-slate-950/60 p-6">
          <h4 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">{t.detailTitle}</h4>
          <p className="whitespace-pre-wrap text-sm font-light leading-relaxed text-slate-300">{analysis || t.noSummary}</p>
        </div>
      )}

      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={open ? detailId : undefined}
        className="flex w-full items-center justify-center gap-2 border-t border-slate-800 bg-slate-800/30 py-2.5 text-xs font-bold uppercase tracking-wider text-slate-500 transition-colors hover:text-slate-300"
      >
        {open ? t.hideDetail : t.showDetail}
        <svg viewBox="0 0 24 24" className={`size-3.5 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
    </article>
  )
}
