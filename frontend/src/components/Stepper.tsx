/**
 * Author: Joonyoung Ki
 *
 * Three-step progress indicator (Upload -> Preferences -> Results).
 */
import { Check } from 'lucide-react'
import type { Translation } from '../lib/i18n'

/** Progress state of one step. */
export type StepStatus = 'done' | 'current' | 'upcoming'

/** Props of `Stepper`; `statuses` holds one state per step. */
interface Props {
  t: Translation
  statuses: [StepStatus, StepStatus, StepStatus]
}

/** Accessible ordered list of steps with connectors; screen readers get the number, label and state of each step. */
export function Stepper({ t, statuses }: Props) {
  const labels = [t.stepUpload, t.stepConditions, t.stepResults]
  const statusText: Record<StepStatus, string> = {
    done: t.stepDone,
    current: t.stepCurrent,
    upcoming: t.stepUpcoming,
  }

  return (
    <ol aria-label={t.stepsLabel} className="flex items-center">
      {labels.map((label, i) => {
        const status = statuses[i]
        return (
          <li
            key={label}
            aria-current={status === 'current' ? 'step' : undefined}
            className={`flex items-center ${i < labels.length - 1 ? 'flex-1' : ''}`}
          >
            <span className="flex items-center gap-2.5">
              <span
                className={`grid size-8 shrink-0 place-items-center rounded-full text-sm font-bold transition-all duration-300 ${
                  status === 'done'
                    ? 'bg-ok text-canvas'
                    : status === 'current'
                      ? 'bg-brand text-brand-on shadow-md ring-4 ring-brand-soft'
                      : 'border border-line-strong bg-surface text-subtle'
                }`}
                aria-hidden="true"
              >
                {status === 'done' ? <Check className="size-4" strokeWidth={3} /> : i + 1}
              </span>
              <span className="hidden min-w-0 sm:block">
                <span
                  className={`block text-sm font-semibold leading-tight ${status === 'upcoming' ? 'text-muted' : 'text-fg'}`}
                >
                  {label}
                </span>
                <span className="block text-xs leading-tight text-subtle">{statusText[status]}</span>
              </span>
              <span className="sr-only">
                {i + 1}. {label} — {statusText[status]}
              </span>
              <span className="text-sm font-semibold text-fg sm:hidden" aria-hidden="true">
                {status === 'current' ? label : ''}
              </span>
            </span>
            {i < labels.length - 1 && (
              <span
                aria-hidden="true"
                className={`mx-3 h-0.5 flex-1 rounded-full transition-colors duration-500 ${
                  status === 'done' ? 'bg-ok' : 'bg-line'
                }`}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}
