/**
 * Author: Joonyoung Ki
 *
 * Purpose: React context object and `useAuth` hook shared by the account UI.
 * The provider component lives in components/AuthProvider.tsx.
 */

import { createContext, useContext } from 'react'
import type { AuthUser, WishlistItem } from './authApi'

export type AuthModalMode = 'login' | 'register'
export type WishlistStatus = 'idle' | 'loading' | 'error' | 'ready'
export type NoticeKind = 'saved' | 'removed' | 'failed' | 'needsLogin'

export interface AuthContextValue {
  /** `undefined` while the session is being checked, `null` for anonymous visitors. */
  user: AuthUser | null | undefined
  wishlist: WishlistItem[]
  wishlistStatus: WishlistStatus
  savedIds: Set<number>
  pendingIds: Set<number>
  modal: AuthModalMode | null
  panelOpen: boolean
  notice: NoticeKind | null
  openModal: (mode: AuthModalMode) => void
  closeModal: () => void
  openPanel: () => void
  closePanel: () => void
  dismissNotice: () => void
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  reloadWishlist: () => void
  toggleSaved: (jobId: number) => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

/** Return the auth context; throws if used outside of AuthProvider. */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
