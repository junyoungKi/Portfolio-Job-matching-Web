/**
 * Author: Joonyoung Ki
 *
 * Helper that builds stable React keys for job match results.
 */
import type { JobMatch } from '../types'

/**
 * Build a unique key for a match.
 *
 * The API has no job id, so the key combines the original result index with company and title.
 * This keeps the open/closed state of a card stable when the list is re-sorted.
 */
export function jobKey(job: JobMatch, index: number): string {
  return `${index}:${job.company}:${job.title}`
}
