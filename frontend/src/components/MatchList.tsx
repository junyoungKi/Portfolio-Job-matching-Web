import type { Translation } from '../lib/i18n'
import { jobKey } from '../lib/jobKey'
import type { Lang, ResultsState } from '../types'
import { MatchCard } from './MatchCard'

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

function Placeholder({ title, body, tone = 'neutral' }: { title: string; body: string; tone?: 'neutral' | 'error' }) {
  return (
    <div
      className={`rounded-3xl border border-dashed p-12 text-center ${
        tone === 'error' ? 'border-rose-500/40 bg-rose-500/5' : 'border-slate-800 bg-slate-900/40'
      }`}
    >
      <p className={`text-base font-bold ${tone === 'error' ? 'text-rose-300' : 'text-slate-300'}`}>{title}</p>
      <p className="mt-2 text-sm text-slate-500">{body}</p>
    </div>
  )
}

function Skeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <div key={i} className="animate-pulse rounded-3xl border border-slate-800 bg-slate-900/60 p-6">
          <div className="mb-4 flex gap-2">
            <div className="h-5 w-24 rounded bg-slate-800" />
            <div className="h-5 w-32 rounded bg-slate-800" />
          </div>
          <div className="mb-3 h-6 w-2/3 rounded bg-slate-800" />
          <div className="h-4 w-full rounded bg-slate-800" />
        </div>
      ))}
    </div>
  )
}

export function MatchList({ t, lang, state, openKeys, selectedSkills, onToggle, onRetry, canRetry }: Props) {
  return (
    <section aria-live="polite" aria-busy={state.status === 'loading'}>
      <div className="mb-6 flex items-center justify-between border-l-4 border-blue-500 pl-4">
        <h2 className="text-sm font-extrabold uppercase tracking-widest text-blue-400">{t.resultTitle}</h2>
        {state.status === 'success' && state.matches.length > 0 && (
          <span className="text-xs font-semibold text-slate-500">{t.resultCount(state.matches.length)}</span>
        )}
      </div>

      {state.status === 'idle' && <Placeholder title={t.emptyIdleTitle} body={t.emptyIdleBody} />}
      {state.status === 'loading' && <Skeleton />}
      {state.status === 'error' && (
        <div role="alert">
          <Placeholder title={state.message} body="" tone="error" />
          {canRetry && (
            <div className="mt-4 text-center">
              <button
                type="button"
                onClick={onRetry}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200 hover:bg-slate-800"
              >
                {t.retry}
              </button>
            </div>
          )}
        </div>
      )}
      {state.status === 'success' &&
        (state.matches.length === 0 ? (
          <Placeholder title={t.emptyResultTitle} body={t.emptyResultBody} />
        ) : (
          <div className="space-y-4">
            {state.matches.map((job, idx) => {
              const key = jobKey(job, idx)
              return (
                <MatchCard
                  key={key}
                  t={t}
                  lang={lang}
                  job={job}
                  open={openKeys.has(key)}
                  selectedSkills={selectedSkills}
                  onToggle={() => onToggle(key)}
                />
              )
            })}
          </div>
        ))}
    </section>
  )
}
