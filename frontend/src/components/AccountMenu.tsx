/**
 * Author: Joonyoung Ki
 *
 * Purpose: Header control for accounts. Shows a log-in button for anonymous
 * visitors and an avatar dropdown (saved jobs, log out) for signed-in users.
 */

import { Heart, LogIn, LogOut, User } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { authTranslations } from '../lib/authI18n'
import { useAuth } from '../lib/authContext'
import type { Lang } from '../types'

interface Props {
  lang: Lang
}

/** Render the account button or dropdown for the header. */
export function AccountMenu({ lang }: Props) {
  const a = authTranslations[lang]
  const { user, wishlist, openModal, openPanel, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (user === undefined) {
    return <div className="skeleton size-10 shrink-0 rounded-lg" aria-hidden="true" />
  }

  if (user === null) {
    return (
      <button
        type="button"
        onClick={() => openModal('login')}
        className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg bg-brand px-3 text-sm font-semibold text-brand-on transition-colors hover:bg-brand-hover sm:px-4"
      >
        <LogIn className="size-4" aria-hidden="true" />
        <span className="hidden sm:inline">{a.login}</span>
        <span className="sr-only sm:hidden">{a.login}</span>
      </button>
    )
  }

  const initial = (user.email.trim()[0] ?? '?').toUpperCase()

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`${a.accountMenu}: ${user.email}`}
        className="relative grid size-10 place-items-center rounded-lg border border-line-strong bg-surface text-sm font-bold text-brand-text transition-colors hover:bg-surface-2"
      >
        {initial}
        {wishlist.length > 0 && (
          <span className="absolute -right-1.5 -top-1.5 grid min-w-5 place-items-center rounded-full bg-bad px-1 text-[11px] font-bold leading-5 text-brand-on">
            {wishlist.length}
          </span>
        )}
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          className="animate-fade-up absolute right-0 top-12 z-40 w-64 overflow-hidden rounded-xl border border-line bg-surface shadow-lg"
        >
          <div className="flex items-center gap-2 border-b border-line px-4 py-3 text-sm">
            <User className="size-4 shrink-0 text-subtle" aria-hidden="true" />
            <span className="min-w-0 truncate font-medium text-fg" title={user.email}>
              {user.email}
            </span>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              openPanel()
            }}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left text-sm text-fg transition-colors hover:bg-surface-2"
          >
            <Heart className="size-4 text-bad" aria-hidden="true" />
            <span className="flex-1">{a.savedJobs}</span>
            <span className="tabular rounded-full bg-surface-2 px-2 py-0.5 text-xs font-semibold text-muted">
              {a.savedJobsCount(wishlist.length)}
            </span>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false)
              void logout()
            }}
            className="flex w-full items-center gap-2.5 border-t border-line px-4 py-2.5 text-left text-sm text-fg transition-colors hover:bg-surface-2"
          >
            <LogOut className="size-4 text-subtle" aria-hidden="true" />
            {a.logout}
          </button>
        </div>
      )}
    </div>
  )
}
