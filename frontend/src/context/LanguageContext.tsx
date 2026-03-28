import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { en } from '../translations/en'
import { ar } from '../translations/ar'

export type Locale = 'en' | 'ar'
export type Translations = typeof en

const translations = { en, ar } as unknown as Record<Locale, Translations>

interface LanguageContextType {
  locale: Locale
  setLocale: (l: Locale) => void
  t: Translations
  dir: 'ltr' | 'rtl'
}

const LanguageContext = createContext<LanguageContextType | null>(null)

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => {
    const saved = localStorage.getItem('smartlearner-locale')
    return (saved === 'ar' ? 'ar' : 'en') as Locale
  })

  useEffect(() => {
    localStorage.setItem('smartlearner-locale', locale)
    document.documentElement.lang = locale === 'ar' ? 'ar' : 'en'
    document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
    document.documentElement.style.fontFamily =
      locale === 'ar' ? "'Cairo', sans-serif" : "'Inter', sans-serif"
  }, [locale])

  const setLocale = (l: Locale) => setLocaleState(l)
  const t = translations[locale]

  return (
    <LanguageContext.Provider
      value={{
        locale,
        setLocale,
        t,
        dir: locale === 'ar' ? 'rtl' : 'ltr',
      }}
    >
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider')
  return ctx
}
