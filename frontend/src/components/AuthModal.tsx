/**
 * Author: Joonyoung Ki
 *
 * Purpose: Accessible login / sign-up dialog with client-side validation,
 * loading state and server error mapping (bad credentials, duplicate email,
 * rate limiting, network failure).
 */

import { AlertCircle, Eye, EyeOff, Loader2, Lock, Mail, X } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../lib/api'
import { authTranslations } from '../lib/authI18n'
import type { AuthTranslation } from '../lib/authI18n'
import { useAuth } from '../lib/authContext'
import type { AuthModalMode } from '../lib/authContext'
import type { Lang } from '../types'

interface Props {
  lang: Lang
  mode: AuthModalMode
}

const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/

const fieldClass =
  'h-11 w-full rounded-lg border border-line-strong bg-surface pl-10 pr-3 text-sm text-fg placeholder:text-subtle transition-shadow focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand-soft disabled:opacity-60'

/** Return a localized validation message for the form, or null if it is valid. */
function validate(email: string, password: string, mode: AuthModalMode, a: AuthTranslation): string | null {
  if (!EMAIL_RE.test(email.trim()) || email.trim().length > 254) return a.errEmail
  if (mode === 'register') {
    if (password.length < 8) return a.errPasswordShort
    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) return a.errPasswordWeak
  } else if (password.length === 0) {
    return a.errCredentials
  }
  return null
}

/** Map a failed auth request to a localized message. */
function describe(e: unknown, mode: AuthModalMode, a: AuthTranslation): string {
  if (e instanceof ApiError) {
    if (e.status === 0) return a.errNetwork
    if (e.status === 401) return a.errCredentials
    if (e.status === 409) return a.errEmailTaken
    if (e.status === 422) return mode === 'register' ? a.errPasswordWeak : a.errCredentials
    if (e.status === 429) return a.errRateLimit
    if (e.status === 503) return a.errNotConfigured
  }
  return a.errGeneric
}

/** Render the login or sign-up dialog. */
export function AuthModal({ lang, mode }: Props) {
  const a = authTranslations[lang]
  const { login, register, closeModal, openModal } = useAuth()
  const titleId = useId()
  const errorId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const emailRef = useRef<HTMLInputElement>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    emailRef.current?.focus()
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeModal()
        return
      }
      const dialog = dialogRef.current
      if (e.key !== 'Tab' || !dialog) return
      const focusable = dialog.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled])')
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const active = document.activeElement
      if (!dialog.contains(active)) {
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
  }, [closeModal])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    const problem = validate(email, password, mode, a)
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const fn = mode === 'login' ? login : register
      await fn(email.trim(), password)
    } catch (err) {
      setError(describe(err, mode, a))
      setBusy(false)
    }
  }

  const isLogin = mode === 'login'

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) closeModal()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="animate-fade-up w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-lg sm:p-8"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id={titleId} className="text-xl font-bold tracking-tight text-fg">
              {isLogin ? a.loginTitle : a.registerTitle}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-muted">{isLogin ? a.loginBody : a.registerBody}</p>
          </div>
          <button
            type="button"
            onClick={closeModal}
            aria-label={a.close}
            className="grid size-9 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-fg"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>

        <form onSubmit={submit} noValidate className="mt-6 space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold text-muted">{a.emailLabel}</span>
            <span className="relative block">
              <Mail className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden="true" />
              <input
                ref={emailRef}
                type="email"
                inputMode="email"
                autoComplete="email"
                maxLength={254}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={a.emailPlaceholder}
                disabled={busy}
                aria-invalid={error !== null}
                aria-describedby={error ? errorId : undefined}
                className={fieldClass}
              />
            </span>
          </label>

          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold text-muted">{a.passwordLabel}</span>
            <span className="relative block">
              <Lock className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-subtle" aria-hidden="true" />
              <input
                type={showPw ? 'text' : 'password'}
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={busy}
                aria-invalid={error !== null}
                aria-describedby={error ? errorId : undefined}
                className={`${fieldClass} pr-11`}
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? a.hidePassword : a.showPassword}
                aria-pressed={showPw}
                className="absolute right-1.5 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-md text-subtle transition-colors hover:text-fg"
              >
                {showPw ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
              </button>
            </span>
            {!isLogin && <span className="mt-1.5 block text-xs text-subtle">{a.passwordHint}</span>}
          </label>

          {error && (
            <p
              id={errorId}
              role="alert"
              className="flex items-start gap-2 rounded-xl border border-bad/40 bg-bad-soft px-3.5 py-2.5 text-sm font-medium text-bad"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-brand text-sm font-semibold text-brand-on transition-colors hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-70"
          >
            {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
            {busy ? a.submitting : isLogin ? a.submitLogin : a.submitRegister}
          </button>
        </form>

        <button
          type="button"
          onClick={() => openModal(isLogin ? 'register' : 'login')}
          disabled={busy}
          className="mt-5 w-full text-center text-sm font-medium text-brand-text hover:underline disabled:opacity-60"
        >
          {isLogin ? a.switchToRegister : a.switchToLogin}
        </button>
      </div>
    </div>
  )
}
