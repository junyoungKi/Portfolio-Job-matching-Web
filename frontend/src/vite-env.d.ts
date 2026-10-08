/**
 * Author: Joonyoung Ki
 *
 * Type declarations for Vite environment variables.
 *
 * Declares ``VITE_API_BASE_URL`` (optional backend origin) so that ``import.meta.env`` is type-checked.
 */
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
