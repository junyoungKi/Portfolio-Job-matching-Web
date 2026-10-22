/**
 * Author: Joonyoung Ki
 *
 * Purpose: Renders the account overlays (login/sign-up dialog, saved-jobs
 * panel) and a transient status toast. Mount once near the app root.
 */

import { CheckCircle2, Info, TriangleAlert, X } from 'lucide-react'
import { useEffect } from 'react'
import { authTranslations } from '../lib/authI18n'
import { useAuth } from '../lib/authContext'
import type { Lang } from '../types'
import { AuthModal } from './AuthModal'
import { WishlistPanel } from './WishlistPanel'

interface Props {
  lang: Lang
}

/** Render account dialogs and the notification toast. */
export function AuthLayer({ lang }: Props) {
  const a = authTranslations[lang]
  const { modal, panelOpen, user, notice, dismissNotice } = useAuth()

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(dismissNotice, 4000)
    return () => window.clearTimeout(timer)
  }, [notice, dismissNotice])

  const messages = {
    saved: a.savedToast,
    removed: a.removedToast,
    failed: a.saveFailed,
    needsLogin: a.saveNeedsLogin,
  } as const
  const Icon = notice === 'failed' ? TriangleAlert : notice === 'needsLogin' ? Info : CheckCircle2
  const tone = notice === 'failed' ? 'border-bad/40 text-bad' : 'border-line-strong text-fg'

  return (
    <>
      {modal && !user && <AuthModal key={modal} lang={lang} mode={modal} />}
      {panelOpen && user && <WishlistPanel lang={lang} />}
      {notice && (
        <div
          role="status"
          className={`animate-fade-up fixed bottom-5 left-1/2 z-[60] flex w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 items-center gap-2.5 rounded-xl border bg-surface px-4 py-3 text-sm font-medium shadow-lg ${tone}`}
        >
          <Icon className="size-4 shrink-0" aria-hidden="true" />
          <span className="flex-1">{messages[notice]}</span>
          <button
            type="button"
            onClick={dismissNotice}
            aria-label={a.close}
            className="grid size-6 place-items-center rounded-md text-subtle hover:text-fg"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
      )}
    </>
  )
}
