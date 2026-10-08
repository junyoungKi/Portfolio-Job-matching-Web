/**
 * Author: Joonyoung Ki
 *
 * Purpose: Heart toggle shown on each match card to save or un-save a job.
 * Anonymous visitors are prompted to log in instead.
 */

import { Heart } from 'lucide-react'
import { authTranslations } from '../lib/authI18n'
import { useAuth } from '../lib/authContext'
import type { Lang } from '../types'

interface Props {
  jobId: number | undefined
  lang: Lang
}

/** Render the save/un-save heart button for one job posting. */
export function WishlistButton({ jobId, lang }: Props) {
  const a = authTranslations[lang]
  const { savedIds, pendingIds, toggleSaved } = useAuth()
  if (jobId === undefined) return null

  const saved = savedIds.has(jobId)
  const pending = pendingIds.has(jobId)
  const label = saved ? a.unsave : a.save

  return (
    <button
      type="button"
      onClick={() => void toggleSaved(jobId)}
      aria-pressed={saved}
      aria-label={label}
      title={label}
      disabled={pending}
      className={`grid size-9 shrink-0 place-items-center rounded-full border transition-all disabled:opacity-60 ${
        saved
          ? 'border-bad/40 bg-bad-soft text-bad hover:bg-bad-soft'
          : 'border-line-strong bg-surface text-muted hover:border-bad/50 hover:text-bad'
      }`}
    >
      <Heart className={`size-[18px] ${saved ? 'fill-current' : ''}`} aria-hidden="true" />
    </button>
  )
}
