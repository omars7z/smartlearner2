import { useEffect, useState } from 'react'

type AccentKey =
  | 'ocean'
  | 'cyan'
  | 'violet'
  | 'rose'
  | 'emerald'
  | 'amber'
  | 'coral'
  | 'magenta'
  | 'indigo'
  | 'lime'
  | 'sky'
  | 'slate'

interface AccentConfig {
  primary: string
  secondary: string
}

const ACCENT_MAP: Record<AccentKey, AccentConfig> = {
  ocean: { primary: '#3B82F6', secondary: '#06B6D4' }, // default
  cyan: { primary: '#06B6D4', secondary: '#38BDF8' },
  violet: { primary: '#8B5CF6', secondary: '#EC4899' },
  rose: { primary: '#F43F5E', secondary: '#F97316' },
  emerald: { primary: '#10B981', secondary: '#84CC16' },
  amber: { primary: '#F59E0B', secondary: '#F97316' },
  coral: { primary: '#F97316', secondary: '#FDBA74' },
  magenta: { primary: '#EC4899', secondary: '#F97316' },
  indigo: { primary: '#6366F1', secondary: '#8B5CF6' },
  lime: { primary: '#84CC16', secondary: '#22C55E' },
  sky: { primary: '#38BDF8', secondary: '#06B6D4' },
  slate: { primary: '#64748B', secondary: '#94A3B8' },
}

const STORAGE_KEY = 'smartlearner_accent'

export function useAccentTheme() {
  const [accent, setAccentState] = useState<AccentKey>(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as AccentKey | null
    if (saved && ACCENT_MAP[saved]) return saved
    return 'ocean'
  })

  useEffect(() => {
    const cfg = ACCENT_MAP[accent]
    document.documentElement.style.setProperty('--accent-primary', cfg.primary)
    document.documentElement.style.setProperty('--accent-secondary', cfg.secondary)
    localStorage.setItem(STORAGE_KEY, accent)
  }, [accent])

  const setAccent = (key: AccentKey) => {
    if (!ACCENT_MAP[key]) return
    setAccentState(key)
  }

  const { primary, secondary } = ACCENT_MAP[accent]

  return {
    accentKey: accent,
    accentPrimary: primary,
    accentSecondary: secondary,
    setAccent,
    options: ACCENT_MAP,
  }
}

