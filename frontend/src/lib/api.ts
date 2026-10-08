import type { Filters, JobMatch, ProcessResumeResponse, StatsResponse } from '../types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

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

export function fetchStats(signal?: AbortSignal): Promise<StatsResponse> {
  return request<StatsResponse>('/stats', { signal })
}

export function processResume(
  file: File,
  keyword: string,
  location: string,
  signal?: AbortSignal,
): Promise<ProcessResumeResponse> {
  const form = new FormData()
  form.append('file', file)
  const qs = new URLSearchParams({ keyword, location })
  return request<ProcessResumeResponse>(`/process-resume?${qs}`, {
    method: 'POST',
    body: form,
    signal,
  })
}

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
