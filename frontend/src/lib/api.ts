/**
 * Author: Joonyoung Ki
 *
 * HTTP client for the FastAPI backend.
 *
 * Wraps ``fetch`` with a base URL (``VITE_API_BASE_URL``, empty for same-origin / Vite proxy), error
 * normalisation into ``ApiError`` and typed helpers for the ``/stats``, ``/process-resume`` and
 * ``/match/{id}`` endpoints.
 */
import type { Filters, JobMatch, ProcessResumeResponse, StatsResponse } from '../types'

/** Backend origin without a trailing slash; empty means same origin (or the Vite dev proxy). */
const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

/** Error thrown for failed requests; `status` is the HTTP status, or 0 when the network request itself failed. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Perform a request and parse the JSON body as `T`.
 *
 * Aborted requests rethrow the original `AbortError`; other failures become an `ApiError` that carries the
 * server-provided `detail` message when available.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, init)
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
  return (await res.json()) as T
}

/** Fetch the total number of collected job postings. */
export function fetchStats(signal?: AbortSignal): Promise<StatsResponse> {
  return request<StatsResponse>('/stats', { signal })
}

/** Upload a PDF resume with the selected location; resolves with the stored resume id. */
export function processResume(
  file: File,
  location: string,
  signal?: AbortSignal,
): Promise<ProcessResumeResponse> {
  const form = new FormData()
  form.append('file', file)
  const qs = new URLSearchParams({ location })
  return request<ProcessResumeResponse>(`/process-resume?${qs}`, {
    method: 'POST',
    body: form,
    signal,
  })
}

/** Fetch the top job matches for a stored resume, applying the selected filters as repeated query parameters. */
export function fetchMatches(
  resumeId: number,
  filters: Filters,
  signal?: AbortSignal,
): Promise<JobMatch[]> {
  const qs = new URLSearchParams()
  filters.levels.forEach((v) => qs.append('levels', v))
  filters.types.forEach((v) => qs.append('types', v))
  filters.skills.forEach((v) => qs.append('skills', v))
  const query = qs.toString()
  return request<JobMatch[]>(`/match/${resumeId}${query ? `?${query}` : ''}`, { signal })
}
