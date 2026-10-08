import { Database, LineChart, Monitor, Moon, SlidersHorizontal, Sun } from 'lucide-react'
import type { RefObject } from 'react'
import { AccountMenu } from './AccountMenu'
import type { Translation } from '../lib/i18n'
import type { ThemePref } from '../lib/theme'
import type { Lang } from '../types'

interface Props {
  t: Translation
  lang: Lang
  onLangChange: (lang: Lang) => void
  themePref: ThemePref
  onThemeChange: (pref: ThemePref) => void
  totalJobs: number | null
  activeFilterCount: number
  onOpenFilters: () => void
  filterTriggerRef: RefObject<HTMLButtonElement | null>
}

const segmentBase =
  'inline-flex items-center justify-center rounded-md text-xs font-semibold transition-colors'

export function Header({
  t,
  lang,
  onLangChange,
  themePref,
  onThemeChange,
  totalJobs,
  activeFilterCount,
  onOpenFilters,
  filterTriggerRef,
}: Props) {
  const themes: { pref: ThemePref; label: string; icon: typeof Sun }[] = [
    { pref: 'system', label: t.themeSystem, icon: Monitor },
    { pref: 'light', label: t.themeLight, icon: Sun },
    { pref: 'dark', label: t.themeDark, icon: Moon },
  ]

  const CurrentThemeIcon = themes.find((x) => x.pref === themePref)?.icon ?? Monitor

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur-xl">
      <nav
        aria-label={t.brand}
        className="mx-auto flex h-16 max-w-7xl items-center gap-2 px-4 sm:gap-3 sm:px-6 lg:px-8"
      >
        <a href="#top" className="group mr-auto flex items-center gap-2.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand text-brand-on shadow-md transition-transform group-hover:scale-105">
            <LineChart className="size-5" strokeWidth={2.4} aria-hidden="true" />
          </span>
          <span className="hidden min-[420px]:block">
            <span className="block text-[15px] font-bold leading-tight tracking-tight text-fg">{t.brand}</span>
            <span className="block text-[11px] font-medium leading-tight text-subtle">{t.brandTag}</span>
          </span>
        </a>

        <div
          className="flex shrink-0 items-center gap-2 whitespace-nowrap rounded-full border border-line bg-surface-2 py-1.5 pl-2.5 pr-3.5 text-sm"
          title={t.navJobs}
        >
          <Database className="size-4 text-brand-text" aria-hidden="true" />
          <span className="hidden text-muted md:inline">{t.navJobs}</span>
          <span className="sr-only md:hidden">{t.navJobs}</span>
          <strong className="tabular font-bold text-fg" aria-live="polite">
            {totalJobs === null ? '—' : totalJobs.toLocaleString()}
          </strong>
        </div>

        <div role="group" aria-label={t.language} className="flex shrink-0 rounded-lg border border-line bg-surface-2 p-0.5">
          {(['ko', 'en'] as const).map((code) => (
            <button
              key={code}
              type="button"
              onClick={() => onLangChange(code)}
              aria-pressed={lang === code}
              aria-label={code === 'ko' ? '한국어' : 'English'}
              className={`${segmentBase} h-8 px-2.5 whitespace-nowrap ${
                lang === code ? 'bg-surface text-fg shadow-sm' : 'text-muted hover:text-fg'
              }`}
            >
              {code === 'ko' ? 'KO' : 'EN'}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => onThemeChange(themes[(themes.findIndex((x) => x.pref === themePref) + 1) % themes.length].pref)}
          aria-label={`${t.themeLabel}: ${themes.find((x) => x.pref === themePref)?.label}`}
          className="grid size-10 shrink-0 place-items-center rounded-lg border border-line bg-surface-2 text-brand-text transition-colors hover:bg-surface sm:hidden"
        >
          <CurrentThemeIcon className="size-4" aria-hidden="true" />
        </button>
        <div role="group" aria-label={t.themeLabel} className="hidden shrink-0 rounded-lg border border-line bg-surface-2 p-0.5 sm:flex">
          {themes.map(({ pref, label, icon: Icon }) => (
            <button
              key={pref}
              type="button"
              onClick={() => onThemeChange(pref)}
              aria-pressed={themePref === pref}
              aria-label={label}
              title={label}
              className={`${segmentBase} size-8 ${
                themePref === pref ? 'bg-surface text-brand-text shadow-sm' : 'text-muted hover:text-fg'
              }`}
            >
              <Icon className="size-4" aria-hidden="true" />
            </button>
          ))}
        </div>

        <AccountMenu lang={lang} />

        <button
          ref={filterTriggerRef}
          type="button"
          onClick={onOpenFilters}
          aria-label={t.openFilters}
          className="relative grid size-10 shrink-0 place-items-center rounded-lg border border-line-strong bg-surface text-fg transition-colors hover:bg-surface-2 lg:hidden"
        >
          <SlidersHorizontal className="size-4" aria-hidden="true" />
          {activeFilterCount > 0 && (
            <span className="absolute -right-1.5 -top-1.5 grid min-w-5 place-items-center rounded-full bg-brand px-1 text-[11px] font-bold leading-5 text-brand-on">
              {activeFilterCount}
            </span>
          )}
        </button>
      </nav>
    </header>
  )
}
