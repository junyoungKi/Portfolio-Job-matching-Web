import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'

export type ThemePref = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'theme'
const QUERY = '(prefers-color-scheme: dark)'

function readPref(): ThemePref {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // storage unavailable: fall back to following the system
  }
  return 'system'
}

function subscribeSystem(onChange: () => void) {
  const mq = window.matchMedia(QUERY)
  mq.addEventListener('change', onChange)
  return () => mq.removeEventListener('change', onChange)
}

const systemDark = () => window.matchMedia(QUERY).matches

export function useTheme() {
  const [pref, setPrefState] = useState<ThemePref>(readPref)
  const prefersDark = useSyncExternalStore(subscribeSystem, systemDark, () => false)
  const dark = pref === 'dark' || (pref === 'system' && prefersDark)

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', dark)
    root.style.colorScheme = dark ? 'dark' : 'light'
  }, [dark])

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
