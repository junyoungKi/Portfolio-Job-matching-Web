/**
 * Author: Joonyoung Ki
 *
 * Purpose: Holds the session and wishlist state for the whole app and exposes
 * it through AuthContext. Anonymous visitors keep full access to resume
 * analysis; the session is only used for saving jobs.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  addWishlist,
  fetchMe,
  fetchWishlist,
  loginRequest,
  logoutRequest,
  registerRequest,
  removeWishlist,
} from '../lib/authApi'
import type { AuthUser, WishlistItem } from '../lib/authApi'
import { AuthContext } from '../lib/authContext'
import type { AuthModalMode, NoticeKind, WishlistStatus } from '../lib/authContext'

interface Props {
  children: ReactNode
}

/** Provide authentication and wishlist state to the component tree. */
export function AuthProvider({ children }: Props) {
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined)
  const [wishlist, setWishlist] = useState<WishlistItem[]>([])
  const [wishlistStatus, setWishlistStatus] = useState<WishlistStatus>('idle')
  const [pendingIds, setPendingIds] = useState<Set<number>>(new Set())
  const [modal, setModal] = useState<AuthModalMode | null>(null)
  const [panelOpen, setPanelOpen] = useState(false)
  const [notice, setNotice] = useState<NoticeKind | null>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const pendingRef = useRef<Set<number>>(new Set())

  useEffect(() => {
    const controller = new AbortController()
    fetchMe(controller.signal)
      .then(setUser)
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setUser(null)
      })
    return () => controller.abort()
  }, [])

  const userId = user?.id ?? null
  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    fetchWishlist(controller.signal)
      .then((items) => {
        setWishlist(items)
        setWishlistStatus('ready')
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setWishlistStatus('error')
      })
    return () => controller.abort()
  }, [userId, reloadTick])

  const savedIds = useMemo(() => new Set(wishlist.map((w) => w.id)), [wishlist])

  const openModal = useCallback((mode: AuthModalMode) => setModal(mode), [])
  const closeModal = useCallback(() => setModal(null), [])
  const openPanel = useCallback(() => setPanelOpen(true), [])
  const closePanel = useCallback(() => setPanelOpen(false), [])
  const dismissNotice = useCallback(() => setNotice(null), [])

  const reloadWishlist = useCallback(() => {
    setWishlistStatus('loading')
    setReloadTick((n) => n + 1)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const next = await loginRequest(email, password)
    setWishlistStatus('loading')
    setUser(next)
    setModal(null)
  }, [])

  const register = useCallback(async (email: string, password: string) => {
    const next = await registerRequest(email, password)
    setWishlistStatus('loading')
    setUser(next)
    setModal(null)
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      setUser(null)
      setWishlist([])
      setWishlistStatus('idle')
      setPanelOpen(false)
    }
  }, [])

  const toggleSaved = useCallback(
    async (jobId: number) => {
      if (!user) {
        setNotice('needsLogin')
        setModal('login')
        return
      }
      if (pendingRef.current.has(jobId)) return
      pendingRef.current.add(jobId)
      setPendingIds(new Set(pendingRef.current))
      const wasSaved = wishlist.some((w) => w.id === jobId)
      try {
        if (wasSaved) {
          await removeWishlist(jobId)
          setWishlist((prev) => prev.filter((w) => w.id !== jobId))
          setNotice('removed')
        } else {
          const item = await addWishlist(jobId)
          setWishlist((prev) => (prev.some((w) => w.id === jobId) ? prev : [item, ...prev]))
          setNotice('saved')
        }
      } catch {
        setNotice('failed')
      } finally {
        pendingRef.current.delete(jobId)
        setPendingIds(new Set(pendingRef.current))
      }
    },
    [user, wishlist],
  )

  const value = useMemo(
    () => ({
      user,
      wishlist,
      wishlistStatus,
      savedIds,
      pendingIds,
      modal,
      panelOpen,
      notice,
      openModal,
      closeModal,
      openPanel,
      closePanel,
      dismissNotice,
      login,
      register,
      logout,
      reloadWishlist,
      toggleSaved,
    }),
    [
      user, wishlist, wishlistStatus, savedIds, pendingIds, modal, panelOpen, notice,
      openModal, closeModal, openPanel, closePanel, dismissNotice, login, register, logout,
      reloadWishlist, toggleSaved,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
