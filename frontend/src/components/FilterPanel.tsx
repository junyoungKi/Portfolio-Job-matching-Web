import { useState } from 'react'
import type { Translation } from '../lib/i18n'
import { DEFAULT_FILTERS, LEVEL_OPTIONS, SKILL_OPTIONS, TYPE_OPTIONS } from '../types'
import type { Filters } from '../types'

interface Props {
  t: Translation
  filters: Filters
  disabled?: boolean
  canReapply: boolean
  onChange: (filters: Filters) => void
  onReapply: () => void
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
  columns?: boolean
  disabled?: boolean
  onToggle: (value: string) => void
}

function CheckGroup({ label, name, options, selected, display, columns, disabled, onToggle }: GroupProps) {
  return (
    <fieldset disabled={disabled}>
      <legend className="mb-3 text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</legend>
      <div className={columns ? 'grid grid-cols-2 gap-2' : 'flex flex-col gap-2'}>
        {options.map((opt) => (
          <label key={opt} className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              name={name}
              value={opt}
              checked={selected.includes(opt)}
              onChange={() => onToggle(opt)}
              className="size-4 cursor-pointer rounded border-slate-600 bg-slate-900 accent-blue-500"
            />
            {display?.[opt] ?? opt}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export function FilterPanel({ t, filters, disabled, canReapply, onChange, onReapply }: Props) {
  const [open, setOpen] = useState(false)
  const activeCount = filters.levels.length + filters.types.length + filters.skills.length

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="advanced-filters"
        className="flex items-center gap-2 text-sm font-bold text-blue-400 hover:text-blue-300"
      >
        <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" />
          <circle cx="16" cy="6" r="2" />
          <circle cx="10" cy="12" r="2" />
          <circle cx="18" cy="18" r="2" />
        </svg>
        {t.filterTitle}
        <span className="rounded-full bg-blue-500/15 px-2 py-0.5 text-[11px] text-blue-300">{activeCount}</span>
        <svg viewBox="0 0 24 24" className={`size-4 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div id="advanced-filters" className="mt-4 rounded-2xl border border-slate-800 bg-slate-950/50 p-5">
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
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
              columns
              disabled={disabled}
              onToggle={(v) => onChange({ ...filters, skills: toggle(filters.skills, v) })}
            />
          </div>
          <div className="mt-5 flex flex-wrap items-center justify-end gap-2 border-t border-slate-800 pt-4">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange(DEFAULT_FILTERS)}
              className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-400 hover:text-slate-200 disabled:cursor-not-allowed"
            >
              {t.resetFilters}
            </button>
            <button
              type="button"
              disabled={disabled || !canReapply}
              onClick={onReapply}
              className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {t.applyFilters}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
