/**
 * Author: Joonyoung Ki
 *
 * Root component of the Smart Job AI dashboard.
 *
 * Owns all application state (language, theme, form inputs, filters, results) and the data flow:
 * upload a resume -> store it via ``/process-resume`` -> fetch matches via ``/match/{id}`` -> render them.
 * Also manages the mobile filter drawer (focus handling, Escape to close, scroll lock) and aborts stale requests.
 */
import { AlertCircle } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { FilterPanel } from './components/FilterPanel'
import { Header } from './components/Header'
import { Hero } from './components/Hero'
import { MatchList } from './components/MatchList'
import { StatCards } from './components/StatCards'
import { UploadCard } from './components/UploadCard'
import { ApiError, fetchMatches, fetchStats, processResume } from './lib/api'
import { translations } from './lib/i18n'
import { useTheme } from './lib/theme'
import type { Translation } from './lib/i18n'
import { DEFAULT_FILTERS } from './types'
import type { Filters, Lang, ResultsState } from './types'

/** Pick the initial UI language: the saved choice, otherwise Korean for Korean browsers and English for the rest. */
function initialLang(): Lang {
  const saved = localStorage.getItem('lang')
  if (saved === 'ko' || saved === 'en') return saved
  return navigator.language.toLowerCase().startsWith('ko') ? 'ko' : 'en'
}

/** Map an API failure to a localized, user-friendly message (network, not found, or generic server error). */
function describeError(e: unknown, t: Translation): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return t.errNetwork
    if (e.status === 404) return t.errNotFound
  }
  return t.errServer
}

/** Dashboard page: header, hero, filter sidebar/drawer, upload form, stat cards and match list. */
export default function App() {
  const [lang, setLang] = useState<Lang>(initialLang)
  const t = translations[lang]
  const theme = useTheme()

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
  const [filtersOpen, setFiltersOpen] = useState(false)
  const filterTriggerRef = useRef<HTMLButtonElement>(null)
  const filterCloseRef = useRef<HTMLButtonElement>(null)

/** Total number of selected filter options (shown as a badge on the mobile filter button). */
  const activeFilterCount = filters.levels.length + filters.types.length + filters.skills.length

/** Close the mobile filter drawer and return focus to the button that opened it. */
  const closeFilters = useCallback(() => {
    setFiltersOpen((wasOpen) => {
      if (wasOpen) filterTriggerRef.current?.focus()
      return false
    })
  }, [])

  // While the drawer is open: focus its close button, close on Escape and lock page scroll on mobile.
  useEffect(() => {
    if (!filtersOpen) return
    filterCloseRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeFilters()
    }
    const isMobile = !window.matchMedia('(min-width: 1024px)').matches
    const prevOverflow = document.body.style.overflow
    if (isMobile) document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [filtersOpen, closeFilters])

/** True while an upload or match request is in flight. */
  const loading = results.status === 'loading'

  // Persist the language and mirror it on <html lang> for accessibility.
  useEffect(() => {
    localStorage.setItem('lang', lang)
    document.documentElement.lang = lang
  }, [lang])

/** Reload the total job count; failures are ignored because the counter is not critical. */
  const refreshStats = useCallback(() => {
    fetchStats()
      .then((data) => setTotalJobs(data.total_jobs))
      .catch(() => {
        // the header counter is non-critical; leave the placeholder
      })
  }, [])

  // Load the job counter once on mount.
  useEffect(() => {
    const controller = new AbortController()
    fetchStats(controller.signal)
      .then((data) => setTotalJobs(data.total_jobs))
      .catch(() => {
        // the header counter is non-critical; leave the placeholder
      })
    return () => controller.abort()
  }, [])

  // Abort any in-flight request when the component unmounts.
  useEffect(() => () => abortRef.current?.abort(), [])

/** Fetch matches for a stored resume and reset per-card state; remembers which skills were applied for highlighting. */
  const loadMatches = useCallback(
    async (id: number, activeFilters: Filters, signal: AbortSignal) => {
      const matches = await fetchMatches(id, activeFilters, signal)
      setAppliedSkills(activeFilters.skills)
      setOpenKeys(new Set())
      setResults({ status: 'success', matches })
    },
    [],
  )

/** Run an async job as the single active request: abort the previous one, show the loading state, map errors to the error state and refresh the stats afterwards. */
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

/** Validate the form, upload the resume, then load its matches. */
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

/** Re-fetch matches for the already stored resume with the current filters (no new upload). */
  const handleReapply = () => {
    if (resumeId === null) return
    void run((signal) => loadMatches(resumeId, filters, signal))
  }

/** Store the selected file; a new file invalidates the previously stored resume. */
  const handleFile = (next: File | null) => {
    setFile(next)
    setFormError(null)
    setResumeId(null)
  }

/** Show or hide a match card's detail panel. */
  const toggleOpen = (key: string) =>
    setOpenKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <div className="flex min-h-screen flex-col">
      <Header
        t={t}
        lang={lang}
        onLangChange={setLang}
        themePref={theme.pref}
        onThemeChange={theme.setPref}
        totalJobs={totalJobs}
        activeFilterCount={activeFilterCount}
        onOpenFilters={() => setFiltersOpen(true)}
        filterTriggerRef={filterTriggerRef}
      />
      <Hero t={t} />

      <div className="mx-auto grid w-full max-w-7xl flex-1 items-start gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[18.5rem_minmax(0,1fr)] lg:gap-8 lg:px-8 lg:py-10">
        <FilterPanel
          t={t}
          filters={filters}
          disabled={loading}
          canReapply={resumeId !== null}
          activeCount={activeFilterCount}
          mobileOpen={filtersOpen}
          closeRef={filterCloseRef}
          onChange={setFilters}
          onReapply={handleReapply}
          onClose={closeFilters}
        />

        <main className="min-w-0 space-y-8">
          <div>
            <UploadCard
              t={t}
              file={file}
              keyword={keyword}
              location={location}
              loading={loading}
              hasResults={results.status === 'success'}
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
              onSubmit={handleSubmit}
            />
            {formError && (
              <p
                role="alert"
                className="mt-4 flex items-start gap-2 rounded-xl border border-bad/40 bg-bad-soft px-4 py-3 text-sm font-medium text-bad"
              >
                <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {formError}
              </p>
            )}
          </div>

          <StatCards t={t} totalJobs={totalJobs} state={results} />

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

      <footer className="border-t border-line py-6 text-center text-xs text-subtle">{t.footer}</footer>
    </div>
  )
}
