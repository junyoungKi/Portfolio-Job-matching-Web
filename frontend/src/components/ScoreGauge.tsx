import type { CSSProperties } from 'react'
import { scoreColor } from '../lib/score'

interface Props {
  pct: number
  size?: number
  stroke?: number
  label: string
  ariaLabel: string
}

export function ScoreGauge({ pct, size = 88, stroke = 8, label, ariaLabel }: Props) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const clamped = Math.max(0, Math.min(100, pct))
  const color = scoreColor(clamped)

  return (
    <div
      className="relative shrink-0"
      style={{ width: size, height: size }}
      role="img"
      aria-label={ariaLabel}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - clamped / 100)}
          className="gauge-arc"
          style={{ '--gauge-c': c } as CSSProperties}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden="true">
        <span className="tabular text-xl font-extrabold leading-none tracking-tight text-fg">
          {clamped.toFixed(0)}
          <span className="text-xs font-bold text-muted">%</span>
        </span>
        <span className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-subtle">{label}</span>
      </div>
    </div>
  )
}
