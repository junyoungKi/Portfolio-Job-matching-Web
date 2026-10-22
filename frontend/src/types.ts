/**
 * Author: Joonyoung Ki
 *
 * Shared TypeScript types and constants for the dashboard.
 *
 * Describes the API response shapes (``JobMatch``, ``StatsResponse``, ``ProcessResumeResponse``), the filter
 * model and its default values, the option lists shown in the UI, and the state machine of the results panel.
 */
/** Supported UI languages: Korean (`ko`) and English (`en`). */
export type Lang = 'ko' | 'en'

/** One matched job as returned by `GET /match/{id}`, with analyses in both languages. */
export interface JobMatch {
  id?: number
  title: string
  company: string
  location: string
  salary: string
  match_score: number
  summary_ko: string
  analysis_ko: string
  summary_en: string
  analysis_en: string
  skills: string | null
}

/** Response of `GET /stats`. */
export interface StatsResponse {
  total_jobs: number
}

/** Response of `POST /process-resume`; `id` identifies the stored resume. */
export interface ProcessResumeResponse {
  status: string
  id: number
  parsed_text_length: number
  parsed_text_preview: string
}

/** User-selected filters forwarded to `GET /match/{id}` as query parameters. */
export interface Filters {
  levels: string[]
  types: string[]
  skills: string[]
}

/** Experience-level values accepted by the backend filter (must match the stored `experience_level` values). */
export const LEVEL_OPTIONS = ['Entry', 'Junior', 'Mid'] as const
/** Employment-type values accepted by the backend filter (must match the stored `employment_type` values). */
export const TYPE_OPTIONS = ['Full-time', 'Internship', 'Contract'] as const
/** Skills offered as filter chips; matched case-insensitively against each job's skills. */
export const SKILL_OPTIONS = ['Python', 'C++', 'Java', 'React', 'AWS'] as const

/** Locations selectable for the search; 'North America' expands to all hub cities on the backend. */
export const LOCATION_OPTIONS = [
  'North America',
  'Vancouver, BC',
  'Toronto, ON',
  'Montreal, QC',
  'Seattle, WA',
  'San Francisco, CA',
  'Los Angeles, CA',
  'Austin, TX',
  'New York, NY',
] as const

/** Filters applied initially and restored by the reset button. */
export const DEFAULT_FILTERS: Filters = {
  levels: ['Junior'],
  types: ['Full-time'],
  skills: [],
}

/** Lifecycle of the results panel: idle -> loading -> success or error. */
export type ResultsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; matches: JobMatch[] }
