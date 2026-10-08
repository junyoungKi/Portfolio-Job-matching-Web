/**
 * Author: Joonyoung Ki
 *
 * Purpose: Slide-over dialog listing the signed-in user's saved jobs with
 * loading, error (retry) and empty states, and a remove button per job.
 */

import { AlertCircle, Banknote, Building2, Heart, MapPin, RotateCw, X } from 'lucide-react'
import { useEffect, useId, useRef } from 'react'
import { authTranslations } from '../lib/authI18n'
import { useAuth } from '../lib/authContext'
import { parseSkills } from '../lib/skills'
import type { Lang } from '../types'

interface Props {
  lang: Lang
}

/** Render the saved-jobs panel. */
export function WishlistPanel({ lang }: Props) {
  const a = authTranslations[lang]
  const { wishlist, wishlistStatus, pendingIds, closePanel, toggleSaved, reloadWishlist } = useAuth()
  const titleId = useId()
  const panelRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    closeRef.current?.focus()
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    // Window-level handler so Escape and Tab trapping still work after the
    // focused element (e.g. a just-removed item's button) leaves the DOM.
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') {
        closePanel()
        return
      }
      const panel = panelRef.current
      if (e.key !== 'Tab' || !panel) return
      const focusable = panel.querySelectorAll<HTMLElement>('button:not([disabled])')
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (!panel.contains(active)) {
        e.preventDefault()
        first.focus()
      } else if (e.shiftKey && active === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = prevOverflow
      opener?.focus?.()
    }
  }, [closePanel])

  const loading = wishlistStatus === 'idle' || wishlistStatus === 'loading'

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) closePanel()
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="animate-fade-up flex h-full w-full max-w-lg flex-col border-l border-line bg-canvas shadow-lg"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line bg-surface px-5 py-4 sm:px-6">
          <div>
            <h2 id={titleId} className="flex items-center gap-2 text-lg font-bold tracking-tight text-fg">
              <Heart className="size-5 fill-current text-bad" aria-hidden="true" />
              {a.wishlistTitle}
              {wishlistStatus === 'ready' && wishlist.length > 0 && (
                <span className="tabular rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-semibold text-brand-text">
                  {a.savedJobsCount(wishlist.length)}
                </span>
              )}
            </h2>
            <p className="mt-1 text-sm text-muted">{a.wishlistSub}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={closePanel}
            aria-label={a.close}
            className="grid size-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-fg"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-5 sm:px-6" aria-live="polite" aria-busy={loading}>
          {loading && (
            <div className="space-y-3" aria-hidden="true">
              {[0, 1, 2].map((i) => (
                <div key={i} className="space-y-3 rounded-2xl border border-line bg-surface p-5">
                  <div className="skeleton h-5 w-2/3 rounded-md" />
                  <div className="skeleton h-4 w-1/2 rounded-md" />
                  <div className="skeleton h-12 w-full rounded-lg" />
                </div>
              ))}
            </div>
          )}

          {wishlistStatus === 'error' && (
            <div role="alert" className="flex flex-col items-center rounded-2xl border border-dashed border-line-strong bg-surface px-6 py-10 text-center">
              <AlertCircle className="size-8 text-bad" aria-hidden="true" />
              <h3 className="mt-3 text-base font-bold text-fg">{a.wishlistErrorTitle}</h3>
              <button
                type="button"
                onClick={reloadWishlist}
                className="mt-4 inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-brand-on transition-colors hover:bg-brand-hover"
              >
                <RotateCw className="size-4" aria-hidden="true" />
                {a.wishlistRetry}
              </button>
            </div>
          )}

          {wishlistStatus === 'ready' && wishlist.length === 0 && (
            <div className="flex flex-col items-center rounded-2xl border border-dashed border-line-strong bg-surface px-6 py-12 text-center">
              <span className="grid size-14 place-items-center rounded-full bg-bad-soft text-bad">
                <Heart className="size-7" aria-hidden="true" />
              </span>
              <h3 className="mt-4 text-base font-bold text-fg">{a.wishlistEmptyTitle}</h3>
              <p className="mt-1.5 max-w-xs text-sm leading-relaxed text-muted">{a.wishlistEmptyBody}</p>
            </div>
          )}

          {wishlistStatus === 'ready' && wishlist.length > 0 && (
            <ul className="space-y-3">
              {wishlist.map((item) => {
                const summary = lang === 'ko' ? item.summary_ko : item.summary_en
                const skills = parseSkills(item.skills)
                const salary =
                  item.salary && item.salary.trim() !== '' && item.salary !== 'None' ? item.salary : a.salaryUnknown
                return (
                  <li key={item.id} className="rounded-2xl border border-line bg-surface p-5 shadow-sm">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="text-base font-bold leading-snug text-fg">{item.title}</h3>
                      <button
                        type="button"
                        onClick={() => void toggleSaved(item.id)}
                        disabled={pendingIds.has(item.id)}
                        aria-label={`${a.wishlistRemove}: ${item.title ?? ''}`}
                        title={a.wishlistRemove}
                        className="grid size-8 shrink-0 place-items-center rounded-full border border-bad/40 bg-bad-soft text-bad transition-colors hover:bg-surface-2 disabled:opacity-60"
                      >
                        <Heart className="size-4 fill-current" aria-hidden="true" />
                      </button>
                    </div>
                    <ul className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
                      <li className="inline-flex items-center gap-1.5">
                        <Building2 className="size-4 text-subtle" aria-hidden="true" />
                        <span className="font-medium text-fg">{item.company}</span>
                      </li>
                      <li className="inline-flex items-center gap-1.5">
                        <MapPin className="size-4 text-subtle" aria-hidden="true" />
                        {item.location}
                      </li>
                      <li className="inline-flex items-center gap-1.5">
                        <Banknote className="size-4 text-subtle" aria-hidden="true" />
                        <span className="font-medium text-ok">{salary}</span>
                      </li>
                    </ul>
                    <p className="mt-3 rounded-lg bg-surface-2 px-3 py-2.5 text-sm leading-relaxed text-muted">
                      {summary || a.noSummary}
                    </p>
                    {skills.length > 0 && (
                      <ul className="mt-3 flex flex-wrap gap-1.5">
                        {skills.map((s) => (
                          <li key={s} className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-semibold text-muted">
                            {s}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
