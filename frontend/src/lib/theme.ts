/**
 * Author: Joonyoung Ki
 *
 * Light/dark/system theme management.
 *
 * Persists the user's choice in ``localStorage`` and keeps the ``dark`` class and ``color-scheme`` on
 * ``<html>`` in sync with it (or with the OS preference). The inline script in ``index.html`` applies the
 * same logic before first paint to avoid a flash of the wrong theme.
 */
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

/** Theme choice: follow the OS (`system`) or force `light` / `dark`. */
export type ThemePref = 'system' | 'light' | 'dark'

/** `localStorage` key under which an explicit light/dark choice is stored. */
const STORAGE_KEY = 'theme'
/** Media query that reports whether the OS prefers a dark colour scheme. */
const QUERY = '(prefers-color-scheme: dark)'

/** Read the saved preference; fall back to `system` if nothing is saved or storage is unavailable. */
function readPref(): ThemePref {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // storage unavailable: fall back to following the system
  }
  return 'system'
}

/** Subscribe to OS colour-scheme changes (the subscribe function for `useSyncExternalStore`). */
function subscribeSystem(onChange: () => void) {
  const mq = window.matchMedia(QUERY)
  mq.addEventListener('change', onChange)
  return () => mq.removeEventListener('change', onChange)
}

/** Snapshot getter: whether the OS currently prefers dark mode. */
const systemDark = () => window.matchMedia(QUERY).matches

/**
 * React hook that exposes the theme preference, the effective dark flag and a setter.
 *
 * Choosing `system` clears the stored value so the OS preference is followed again.
 */
export function useTheme() {
  const [pref, setPrefState] = useState<ThemePref>(readPref)
  const prefersDark = useSyncExternalStore(subscribeSystem, systemDark, () => false)
  const dark = pref === 'dark' || (pref === 'system' && prefersDark)

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', dark)
    root.style.colorScheme = dark ? 'dark' : 'light'
  }, [dark])

  /** Update the preference state and persist it (or clear it for `system`). */
  const setPref = useCallback((next: ThemePref) => {
    setPrefState(next)
    try {
      if (next === 'system') localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // ignore: preference just won't persist
    }
  }, [])

  return { pref, dark, setPref }
}
