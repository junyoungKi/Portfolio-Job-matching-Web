import type { Lang } from '../types'
import type { Translation } from '../lib/i18n'

interface Props {
  t: Translation
  lang: Lang
  onLangChange: (lang: Lang) => void
  totalJobs: number | null
}

export function Header({ t, lang, onLangChange, totalJobs }: Props) {
  return (
    <header className="flex flex-col gap-6 border-b border-slate-800 pb-8 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex items-center gap-4">
        <div className="grid size-12 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-blue-500 to-violet-600 shadow-lg shadow-blue-900/40">
          <svg viewBox="0 0 24 24" className="size-6 text-white" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 17l6-6 4 4 8-8" />
            <path d="M15 7h6v6" />
          </svg>
        </div>
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-white sm:text-4xl">{t.title}</h1>
          <p className="mt-1 text-xs font-semibold uppercase tracking-widest text-slate-500">{t.subtitle}</p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-6 sm:justify-end">
        <div
          role="group"
          aria-label={t.language}
          className="inline-flex rounded-lg border border-slate-700 bg-slate-900 p-0.5 text-xs font-bold"
        >
          {(['ko', 'en'] as const).map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => onLangChange(code)}
              aria-pressed={lang === code}
              className={`rounded-md px-3 py-1.5 transition-colors ${
                lang === code ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {code === 'ko' ? '한국어' : 'English'}
            </button>
          ))}
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-5 py-3 text-right">
          <div className="text-3xl font-extrabold tabular-nums text-white" aria-live="polite">
            {totalJobs === null ? '---' : totalJobs.toLocaleString()}
          </div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{t.statsLabel}</div>
        </div>
      </div>
    </header>
  )
}
