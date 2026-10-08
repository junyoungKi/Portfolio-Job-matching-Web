import { Check, RotateCcw, SlidersHorizontal, X } from 'lucide-react'
import type { RefObject } from 'react'
import type { Translation } from '../lib/i18n'
import { DEFAULT_FILTERS, LEVEL_OPTIONS, SKILL_OPTIONS, TYPE_OPTIONS } from '../types'
import type { Filters } from '../types'

interface Props {
  t: Translation
  filters: Filters
  disabled?: boolean
  canReapply: boolean
  activeCount: number
  mobileOpen: boolean
  closeRef: RefObject<HTMLButtonElement | null>
  onChange: (filters: Filters) => void
  onReapply: () => void
  onClose: () => void
}

function toggle(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

interface GroupProps {
  label: string
  name: string
  options: readonly string[]
  selected: string[]
  display?: Record<string, string>
  disabled?: boolean
  chips?: boolean
  onToggle: (value: string) => void
}

function CheckGroup({ label, name, options, selected, display, disabled, chips, onToggle }: GroupProps) {
  return (
    <fieldset disabled={disabled} className="min-w-0">
      <legend className="mb-2.5 text-xs font-semibold text-muted">{label}</legend>
      <div className={chips ? 'flex flex-wrap gap-2' : 'flex flex-col gap-1.5'}>
        {options.map((opt) => {
          const checked = selected.includes(opt)
          return (
            <label
              key={opt}
              className={`group relative flex cursor-pointer items-center gap-2.5 text-sm transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[var(--brand-ring)] ${
                chips
                  ? `rounded-full border px-3 py-1.5 font-medium ${
                      checked
                        ? 'border-brand bg-brand-soft text-brand-text'
                        : 'border-line-strong bg-surface text-muted hover:border-brand hover:text-fg'
                    }`
                  : 'rounded-lg px-2 py-1.5 text-fg hover:bg-surface-2'
              } ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}
            >
              <input
                type="checkbox"
                name={name}
                value={opt}
                checked={checked}
                onChange={() => onToggle(opt)}
                className="peer sr-only"
              />
              {!chips && (
                <span
                  className={`grid size-[18px] shrink-0 place-items-center rounded-md border transition-colors ${
                    checked ? 'border-brand bg-brand text-brand-on' : 'border-line-strong bg-surface'
                  }`}
                  aria-hidden="true"
                >
                  {checked && <Check className="size-3" strokeWidth={3.5} />}
                </span>
              )}
              {chips && checked && <Check className="size-3.5" strokeWidth={3} aria-hidden="true" />}
              {display?.[opt] ?? opt}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}

export function FilterPanel({
  t,
  filters,
  disabled,
  canReapply,
  activeCount,
  mobileOpen,
  closeRef,
  onChange,
  onReapply,
  onClose,
}: Props) {
  return (
    <>
      <div
        onClick={onClose}
        aria-hidden="true"
        className={`fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity duration-300 lg:hidden ${
          mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        id="filters"
        aria-label={t.filterTitle}
        className={`z-50 flex flex-col border-line bg-surface max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:w-[min(21rem,88vw)] max-lg:border-r max-lg:shadow-lg max-lg:transition-[transform,visibility] max-lg:duration-300 lg:sticky lg:top-24 lg:rounded-2xl lg:border lg:shadow-md ${
          mobileOpen ? 'max-lg:translate-x-0' : 'max-lg:invisible max-lg:-translate-x-full'
        }`}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="flex items-start gap-2.5">
            <span className="mt-0.5 grid size-8 place-items-center rounded-lg bg-brand-soft text-brand-text" aria-hidden="true">
              <SlidersHorizontal className="size-4" />
            </span>
            <div>
              <h2 className="text-[15px] font-bold leading-tight text-fg">{t.filterTitle}</h2>
              <p className="mt-0.5 text-xs text-subtle">{activeCount > 0 ? t.activeFilters(activeCount) : t.filterSub}</p>
            </div>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label={t.closeFilters}
            className="grid size-9 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-fg lg:hidden"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          <CheckGroup
            label={t.labelExp}
            name="level"
            options={LEVEL_OPTIONS}
            selected={filters.levels}
            display={t.expLevels}
            disabled={disabled}
            onToggle={(v) => onChange({ ...filters, levels: toggle(filters.levels, v) })}
          />
          <CheckGroup
            label={t.labelType}
            name="type"
            options={TYPE_OPTIONS}
            selected={filters.types}
            display={t.typeLevels}
            disabled={disabled}
            onToggle={(v) => onChange({ ...filters, types: toggle(filters.types, v) })}
          />
          <CheckGroup
            label={t.labelSkills}
            name="skill"
            options={SKILL_OPTIONS}
            selected={filters.skills}
            disabled={disabled}
            chips
            onToggle={(v) => onChange({ ...filters, skills: toggle(filters.skills, v) })}
          />
        </div>

        <div className="space-y-2.5 border-t border-line px-5 py-4">
          <button
            type="button"
            disabled={disabled || !canReapply}
            onClick={() => {
              onReapply()
              onClose()
            }}
            className="h-10 w-full rounded-lg bg-brand text-sm font-semibold text-brand-on transition-colors hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            {t.applyFilters}
          </button>
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs leading-snug text-subtle">{!canReapply && t.applyHint}</p>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(DEFAULT_FILTERS)}
              className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-semibold text-muted transition-colors hover:text-fg disabled:cursor-not-allowed"
            >
              <RotateCcw className="size-3" aria-hidden="true" />
              {t.resetFilters}
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
