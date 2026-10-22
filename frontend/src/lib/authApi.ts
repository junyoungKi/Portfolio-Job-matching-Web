/**
 * Author: Joonyoung Ki
 *
 * Purpose: Typed client for the /auth and /wishlist endpoints. All requests use
 * same-origin relative paths (or VITE_API_BASE_URL in development) and include
 * credentials so the httpOnly session cookie is sent.
 */

import { ApiError } from './api'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export interface AuthUser {
  id: number
  email: string
}

export interface WishlistItem {
  id: number
  title: string | null
  company: string | null
  location: string | null
  salary: string | null
  skills: string | null
  summary_ko: string | null
  summary_en: string | null
  saved_at: string
}

/**
 * Perform a credentialed JSON request and map failures to ApiError.
 * Network failures use status 0; HTTP errors carry the server `detail` text.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined) headers.set('Content-Type', 'application/json')

  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...init, headers, credentials: 'include' })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError('network', 0)
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body: unknown = await res.json()
      if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
        detail = body.detail
      }
    } catch {
      // non-JSON error body: keep the HTTP status message
    }
    throw new ApiError(detail, res.status)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** Fetch the current user, resolving to null when the visitor is anonymous. */
export async function fetchMe(signal?: AbortSignal): Promise<AuthUser | null> {
  try {
    return await request<AuthUser>('/auth/me', { signal })
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null
    throw e
  }
}

/** Log in with email and password; the server sets the session cookie. */
export function loginRequest(email: string, password: string): Promise<AuthUser> {
  return request<AuthUser>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
}

/** Create an account; the server also logs the new user in. */
export function registerRequest(email: string, password: string): Promise<AuthUser> {
  return request<AuthUser>('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) })
}

/** Log out and clear the session cookie. */
export function logoutRequest(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' })
}

/** List the current user's saved jobs, newest first. */
export function fetchWishlist(signal?: AbortSignal): Promise<WishlistItem[]> {
  return request<WishlistItem[]>('/wishlist', { signal })
}

/** Save a job posting by id. */
export function addWishlist(jobId: number): Promise<WishlistItem> {
  return request<WishlistItem>('/wishlist', { method: 'POST', body: JSON.stringify({ job_id: jobId }) })
}

/** Remove a saved job posting by id. */
export function removeWishlist(jobId: number): Promise<void> {
  return request<void>(`/wishlist/${jobId}`, { method: 'DELETE' })
}
