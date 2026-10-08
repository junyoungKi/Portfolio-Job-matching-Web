import type { CSSProperties } from 'react'
import { BarChart3, Database, ListChecks, Trophy } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { Translation } from '../lib/i18n'
import { clampPct } from '../lib/score'
import type { ResultsState } from '../types'

interface Props {
  t: Translation
  totalJobs: number | null
  state: ResultsState
}

interface CardProps {
  label: string
  hint: string
  value: string
  icon: LucideIcon
  tone: 'brand' | 'ok' | 'warn' | 'neutral'
  loading?: boolean
  index: number
}

const toneClass: Record<CardProps['tone'], string> = {
  brand: 'bg-brand-soft text-brand-text',
  ok: 'bg-ok-soft text-ok',
  warn: 'bg-warn-soft text-warn',
  neutral: 'bg-surface-2 text-muted',
}

function StatCard({ label, hint, value, icon: Icon, tone, loading, index }: CardProps) {
  return (
    <div
      className="animate-fade-up rounded-2xl border border-line bg-surface p-4 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md sm:p-5"
      style={{ '--i': index } as CSSProperties}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-muted sm:text-sm">{label}</p>
        <span className={`grid size-8 place-items-center rounded-lg ${toneClass[tone]}`} aria-hidden="true">
          <Icon className="size-4" />
        </span>
      </div>
      {loading ? (
        <div className="skeleton mt-3 h-8 w-20 rounded-md" aria-hidden="true" />
      ) : (
        <p className="tabular mt-2 text-2xl font-extrabold tracking-tight text-fg sm:text-[28px]">{value}</p>
      )}
      <p className="mt-1 text-xs text-subtle">{hint}</p>
    </div>
  )
}

export function StatCards({ t, totalJobs, state }: Props) {
  const loading = state.status === 'loading'
  const matches = state.status === 'success' ? state.matches : null
  const scores = matches?.map((m) => clampPct(m.match_score)) ?? []
  const has = scores.length > 0
  const avg = has ? scores.reduce((a, b) => a + b, 0) / scores.length : null
  const best = has ? Math.max(...scores) : null

  const cards: Omit<CardProps, 'index'>[] = [
    {
      label: t.statTotal,
      hint: t.statTotalHint,
      value: totalJobs === null ? '—' : totalJobs.toLocaleString(),
      icon: Database,
      tone: 'brand',
    },
    {
      label: t.statMatched,
      hint: t.statMatchedHint,
      value: matches ? matches.length.toLocaleString() : '—',
      icon: ListChecks,
      tone: 'neutral',
      loading,
    },
    {
      label: t.statAvg,
      hint: t.statAvgHint,
      value: avg === null ? '—' : `${avg.toFixed(1)}%`,
      icon: BarChart3,
      tone: 'warn',
      loading,
    },
    {
      label: t.statBest,
      hint: t.statBestHint,
      value: best === null ? '—' : `${best.toFixed(1)}%`,
      icon: Trophy,
      tone: 'ok',
      loading,
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
      {cards.map((c, i) => (
        <StatCard key={c.label} {...c} index={i} />
      ))}
    </div>
  )
}
