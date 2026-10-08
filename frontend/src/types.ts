export type Lang = 'ko' | 'en'

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

export interface StatsResponse {
  total_jobs: number
}

export interface ProcessResumeResponse {
  status: string
  id: number
  parsed_text_length: number
  parsed_text_preview: string
}

export interface Filters {
  levels: string[]
  types: string[]
  skills: string[]
}

export const LEVEL_OPTIONS = ['Entry', 'Junior', 'Mid'] as const
export const TYPE_OPTIONS = ['Full-time', 'Internship', 'Contract'] as const
export const SKILL_OPTIONS = ['Python', 'C++', 'Java', 'React', 'AWS'] as const

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

export const DEFAULT_FILTERS: Filters = {
  levels: ['Junior'],
  types: ['Full-time'],
  skills: [],
}

export type ResultsState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; matches: JobMatch[] }
