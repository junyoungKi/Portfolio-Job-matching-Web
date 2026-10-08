import { useCallback, useEffect, useRef, useState } from 'react'
import { Header } from './components/Header'
import { MatchList } from './components/MatchList'
import { UploadForm } from './components/UploadForm'
import { ApiError, fetchMatches, fetchStats, processResume } from './lib/api'
import { translations } from './lib/i18n'
import type { Translation } from './lib/i18n'
import { DEFAULT_FILTERS } from './types'
import type { Filters, Lang, ResultsState } from './types'

function initialLang(): Lang {
  const saved = localStorage.getItem('lang')
  if (saved === 'ko' || saved === 'en') return saved
  return navigator.language.toLowerCase().startsWith('ko') ? 'ko' : 'en'
}

function describeError(e: unknown, t: Translation): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return t.errNetwork
    if (e.status === 404) return t.errNotFound
  }
  return t.errServer
}

export default function App() {
  const [lang, setLang] = useState<Lang>(initialLang)
  const t = translations[lang]

  const [totalJobs, setTotalJobs] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [keyword, setKeyword] = useState('')
  const [location, setLocation] = useState('North America')
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [resumeId, setResumeId] = useState<number | null>(null)
  const [appliedSkills, setAppliedSkills] = useState<string[]>([])
  const [formError, setFormError] = useState<string | null>(null)
  const [results, setResults] = useState<ResultsState>({ status: 'idle' })
  const [openKeys, setOpenKeys] = useState<Set<string>>(new Set())
  const abortRef = useRef<AbortController | null>(null)

  const loading = results.status === 'loading'

  useEffect(() => {
    localStorage.setItem('lang', lang)
    document.documentElement.lang = lang
  }, [lang])

  const refreshStats = useCallback(() => {
    fetchStats()
      .then((data) => setTotalJobs(data.total_jobs))
      .catch(() => {
        // the header counter is non-critical; leave the placeholder
      })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetchStats(controller.signal)
      .then((data) => setTotalJobs(data.total_jobs))
      .catch(() => {
        // the header counter is non-critical; leave the placeholder
      })
    return () => controller.abort()
  }, [])

  useEffect(() => () => abortRef.current?.abort(), [])

  const loadMatches = useCallback(
    async (id: number, activeFilters: Filters, signal: AbortSignal) => {
      const matches = await fetchMatches(id, activeFilters, signal)
      setAppliedSkills(activeFilters.skills)
      setOpenKeys(new Set())
      setResults({ status: 'success', matches })
    },
    [],
  )

  const run = useCallback(
    async (job: (signal: AbortSignal) => Promise<void>) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      setFormError(null)
      setResults({ status: 'loading' })
      try {
        await job(controller.signal)
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setResults({ status: 'error', message: describeError(e, t) })
      } finally {
        if (abortRef.current === controller) refreshStats()
      }
    },
    [refreshStats, t],
  )

  const handleSubmit = () => {
    const trimmed = keyword.trim()
    if (!file || !trimmed) {
      setFormError(t.errFill)
      return
    }
    void run(async (signal) => {
      const data = await processResume(file, trimmed, location, signal)
      setResumeId(data.id)
      await loadMatches(data.id, filters, signal)
    })
  }

  const handleReapply = () => {
    if (resumeId === null) return
    void run((signal) => loadMatches(resumeId, filters, signal))
  }

  const handleFile = (next: File | null) => {
    setFile(next)
    setFormError(null)
    setResumeId(null)
  }

  const toggleOpen = (key: string) =>
    setOpenKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6 sm:py-12">
      <Header t={t} lang={lang} onLangChange={setLang} totalJobs={totalJobs} />

      <main className="mt-10 space-y-12">
        <div>
          <UploadForm
            t={t}
            file={file}
            keyword={keyword}
            location={location}
            filters={filters}
            loading={loading}
            hasResume={resumeId !== null}
            onFile={handleFile}
            onInvalidFile={() => setFormError(t.errPdf)}
            onKeyword={(v) => {
              setKeyword(v)
              setResumeId(null)
            }}
            onLocation={(v) => {
              setLocation(v)
              setResumeId(null)
            }}
            onFilters={setFilters}
            onSubmit={handleSubmit}
            onReapply={handleReapply}
          />
          {formError && (
            <p role="alert" className="mt-4 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
              {formError}
            </p>
          )}
        </div>

        <MatchList
          t={t}
          lang={lang}
          state={results}
          openKeys={openKeys}
          selectedSkills={appliedSkills}
          onToggle={toggleOpen}
          onRetry={resumeId !== null ? handleReapply : handleSubmit}
          canRetry={resumeId !== null || (file !== null && keyword.trim() !== '')}
        />
      </main>
    </div>
  )
}
