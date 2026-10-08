import type { FormEvent } from 'react'
import type { Translation } from '../lib/i18n'
import { LOCATION_OPTIONS } from '../types'
import type { Filters } from '../types'
import { FileDropzone } from './FileDropzone'
import { FilterPanel } from './FilterPanel'

interface Props {
  t: Translation
  file: File | null
  keyword: string
  location: string
  filters: Filters
  loading: boolean
  hasResume: boolean
  onFile: (file: File | null) => void
  onInvalidFile: () => void
  onKeyword: (v: string) => void
  onLocation: (v: string) => void
  onFilters: (f: Filters) => void
  onSubmit: () => void
  onReapply: () => void
}

const fieldClass =
  'w-full rounded-xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-white placeholder:text-slate-600 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-60'

export function UploadForm(props: Props) {
  const { t, file, keyword, location, filters, loading, hasResume } = props

  const submit = (e: FormEvent) => {
    e.preventDefault()
    props.onSubmit()
  }

  return (
    <form
      onSubmit={submit}
      className="space-y-6 rounded-3xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl shadow-black/30 backdrop-blur sm:p-8"
    >
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div>
          <label htmlFor="keyword" className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">
            {t.keywordLabel}
          </label>
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
        <div>
          <label htmlFor="location" className="mb-2 block text-xs font-bold uppercase tracking-wider text-slate-400">
            {t.locationLabel}
          </label>
          <select
            id="location"
            value={location}
            disabled={loading}
            onChange={(e) => props.onLocation(e.target.value)}
            className={fieldClass}
          >
            {LOCATION_OPTIONS.map((loc) => (
              <option key={loc} value={loc}>
                {loc === 'North America' ? t.locAll : loc}
              </option>
            ))}
          </select>
        </div>
      </div>

      <FileDropzone t={t} file={file} disabled={loading} onFile={props.onFile} onInvalid={props.onInvalidFile} />

      <FilterPanel
        t={t}
        filters={filters}
        disabled={loading}
        canReapply={hasResume}
        onChange={props.onFilters}
        onReapply={props.onReapply}
      />

      <button
        type="submit"
        disabled={loading}
        className="flex w-full items-center justify-center gap-3 rounded-2xl bg-gradient-to-r from-blue-600 to-violet-600 px-8 py-4 text-base font-extrabold text-white shadow-lg shadow-blue-900/40 transition hover:brightness-110 active:scale-[0.99] disabled:cursor-wait disabled:opacity-70"
      >
        {loading && <span className="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white" aria-hidden="true" />}
        {loading ? t.analyzing : t.btnStart}
      </button>
    </form>
  )
}
