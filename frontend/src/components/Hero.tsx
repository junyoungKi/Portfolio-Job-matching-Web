import { CheckCircle2, Sparkles } from 'lucide-react'
import type { Translation } from '../lib/i18n'
import { ScoreGauge } from './ScoreGauge'

interface Props {
  t: Translation
}

export function Hero({ t }: Props) {
  return (
    <section id="top" className="hero-bg relative overflow-hidden border-b border-line">
      <div className="grid-dots pointer-events-none absolute inset-0" aria-hidden="true" />
      <div className="relative mx-auto grid max-w-7xl items-center gap-10 px-4 py-12 sm:px-6 sm:py-16 lg:grid-cols-[1.25fr_1fr] lg:px-8 lg:py-20">
        <div className="animate-fade-up">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-semibold text-brand-text shadow-sm backdrop-blur">
            <Sparkles className="size-3.5" aria-hidden="true" />
            {t.heroEyebrow}
          </span>
          <h1 className="mt-5 max-w-2xl text-balance text-[28px] font-extrabold leading-[1.2] tracking-tight text-fg sm:text-4xl lg:text-[44px]">
            {t.heroTitle}
          </h1>
          <p className="mt-4 max-w-xl text-pretty text-base leading-relaxed text-muted sm:text-lg">{t.heroBody}</p>
          <ul className="mt-6 flex flex-wrap gap-x-5 gap-y-2.5">
            {t.heroPoints.map((p) => (
              <li key={p} className="flex items-center gap-2 text-sm font-medium text-fg">
                <CheckCircle2 className="size-[18px] text-ok" aria-hidden="true" />
                {p}
              </li>
            ))}
          </ul>
        </div>

        <div className="relative hidden justify-self-end lg:block" aria-hidden="true">
          <div className="animate-float w-[340px] rounded-2xl border border-line bg-surface p-5 shadow-lg">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs font-medium text-subtle">{t.heroPreviewLabel}</p>
                <p className="mt-1 truncate text-lg font-bold text-fg">{t.heroPreviewRole}</p>
                <p className="text-sm text-muted">Vancouver, BC</p>
              </div>
              <ScoreGauge pct={92} size={84} stroke={8} label={t.matchLabel} ariaLabel="" />
            </div>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {['Python', 'AWS', 'Docker'].map((s, i) => (
                <span
                  key={s}
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                    i < 2 ? 'bg-ok-soft text-ok' : 'bg-surface-2 text-muted'
                  }`}
                >
                  {s}
                </span>
              ))}
            </div>
            <div className="mt-4 space-y-2">
              <div className="h-2 w-full rounded-full bg-surface-2" />
              <div className="h-2 w-4/5 rounded-full bg-surface-2" />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
