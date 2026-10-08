import type { JobMatch } from '../types'

export function jobKey(job: JobMatch, index: number): string {
  return `${index}:${job.company}:${job.title}`
}
