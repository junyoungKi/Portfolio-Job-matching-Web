import { ArrowRight, Briefcase, MapPin } from 'lucide-react'
import type { FormEvent } from 'react'
import type { Translation } from '../lib/i18n'
import { LOCATION_OPTIONS } from '../types'
import { FileDropzone } from './FileDropzone'
import { Stepper } from './Stepper'
import type { StepStatus } from './Stepper'

interface Props {
  t: Translation
  file: File | null
  keyword: string
  location: string
  loading: boolean
  hasResults: boolean
  onFile: (file: File | null) => void
  onInvalidFile: () => void
  onKeyword: (v: string) => void
  onLocation: (v: string) => void
  onSubmit: () => void
}

const fieldClass =
  'h-11 w-full rounded-lg border border-line-strong bg-surface pl-10 pr-3 text-sm text-fg placeholder:text-subtle transition-shadow focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand-soft disabled:opacity-60'

function StepHeading({ n, title, hint }: { n: number; title: string; hint?: string }) {
  return (
    <div className="mb-3 flex items-baseline gap-2.5">
      <span className="grid size-5 place-items-center rounded-full bg-brand-soft text-[11px] font-bold text-brand-text" aria-hidden="true">
        {n}
      </span>
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      {hint && <span className="hidden text-xs text-subtle sm:inline">{hint}</span>}
    </div>
  )
}

export function UploadCard(props: Props) {
  const { t, file, keyword, location, loading, hasResults } = props
  const hasKeyword = keyword.trim() !== ''

  let statuses: [StepStatus, StepStatus, StepStatus]
  if (hasResults) statuses = ['done', 'done', 'done']
  else if (loading) statuses = ['done', 'done', 'current']
  else if (!file) statuses = ['current', 'upcoming', 'upcoming']
  else if (!hasKeyword) statuses = ['done', 'current', 'upcoming']
  else statuses = ['done', 'done', 'current']

  const submit = (e: FormEvent) => {
    e.preventDefault()
    props.onSubmit()
  }

  return (
    <form
      onSubmit={submit}
      aria-label={t.btnStart}
      className="rounded-2xl border border-line bg-surface shadow-md"
    >
      <div className="border-b border-line px-5 py-4 sm:px-6">
        <Stepper t={t} statuses={statuses} />
      </div>

      <div className="space-y-6 p-5 sm:p-6">
        <section>
          <StepHeading n={1} title={t.resumeLabel} hint={t.stepUploadHint} />
          <FileDropzone t={t} file={file} disabled={loading} onFile={props.onFile} onInvalid={props.onInvalidFile} />
        </section>

        <section>
          <StepHeading n={2} title={t.stepConditions} hint={t.stepConditionsHint} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label htmlFor="keyword" className="mb-1.5 block text-xs font-medium text-muted">
                {t.keywordLabel}
              </label>
              <div className="relative">
                <Briefcase className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden="true" />
                <input
                  id="keyword"
                  type="text"
                  value={keyword}
                  disabled={loading}
                  placeholder={t.keywordPlaceholder}
                  onChange={(e) => props.onKeyword(e.target.value)}
                  className={fieldClass}
                />
              </div>
            </div>
            <div>
              <label htmlFor="location" className="mb-1.5 block text-xs font-medium text-muted">
                {t.locationLabel}
              </label>
              <div className="relative">
                <MapPin className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden="true" />
                <select
                  id="location"
                  value={location}
                  disabled={loading}
                  onChange={(e) => props.onLocation(e.target.value)}
                  className={`${fieldClass} appearance-none`}
                >
                  {LOCATION_OPTIONS.map((loc) => (
                    <option key={loc} value={loc}>
                      {loc === 'North America' ? t.locAll : loc}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </section>

        <section>
          <StepHeading n={3} title={t.stepResults} hint={t.stepResultsHint} />
          <button
            type="submit"
            disabled={loading}
            className="group flex h-12 w-full items-center justify-center gap-2.5 rounded-xl bg-brand px-6 text-[15px] font-semibold text-brand-on shadow-md transition-all hover:-translate-y-px hover:bg-brand-hover hover:shadow-lg active:translate-y-0 disabled:translate-y-0 disabled:cursor-wait disabled:opacity-80"
          >
            {loading ? (
              <>
                <span className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />
                {t.analyzing}
              </>
            ) : (
              <>
                {hasResults ? t.btnRestart : t.btnStart}
                <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
              </>
            )}
          </button>
        </section>
      </div>
    </form>
  )
}
