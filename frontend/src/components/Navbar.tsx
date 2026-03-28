import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { GraduationCap, Sun, Moon, Menu, X } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { useTheme } from '../context/ThemeContext'

const navLinks = [
  { id: 'home', key: 'home', href: '/' },
  { id: 'features', key: 'features', href: '/#features' },
  { id: 'agents', key: 'agents', href: '/#agents' },
  { id: 'how-it-works', key: 'howItWorks', href: '/#how-it-works' },
  { id: 'about', key: 'about', href: '/#about' },
  { id: 'team', key: 'team', href: '/#team' },
] as const

export default function Navbar() {
  const { locale, setLocale, t } = useLanguage()
  const { theme, toggleTheme } = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)
  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
      className="sticky top-0 z-50 w-full border-b border-slate-200/50 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl"
    >
      <nav className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2">
          <GraduationCap className="h-8 w-8 text-[#3B82F6]" />
          <span className="bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] bg-clip-text text-xl font-bold text-transparent">
            SmartLearner
          </span>
        </Link>

        <div className="hidden md:flex md:items-center md:gap-6">
          {navLinks.map((link) => (
            <a
              key={link.id}
              href={link.href}
              onClick={() => setMobileOpen(false)}
              className="text-slate-600 dark:text-slate-300 hover:text-[#3B82F6] dark:hover:text-cyan-400 transition-colors"
            >
              {t.nav[link.key]}
            </a>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setLocale(locale === 'en' ? 'ar' : 'en')}
            className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            {locale === 'en' ? 'AR' : 'EN'}
          </button>
          <button
            onClick={toggleTheme}
            className="rounded-lg p-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
          <Link
            to="/login"
            className="hidden sm:inline-flex rounded-lg border border-[#3B82F6] px-4 py-2 text-sm font-medium text-[#3B82F6] hover:bg-[#3B82F6]/10 transition-colors"
          >
            {t.nav.login}
          </Link>
          <Link
            to="/register"
            className="hidden sm:inline-flex rounded-lg bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] px-4 py-2 text-sm font-medium text-white shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:scale-105 transition-all"
          >
            {t.nav.getStarted}
          </Link>
          <button
            onClick={() => setMobileOpen((o) => !o)}
            className="md:hidden rounded-lg p-2 text-slate-600 dark:text-slate-300"
          >
            {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden overflow-hidden border-t border-slate-200/50 dark:border-white/10 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl"
          >
            <div className="flex flex-col gap-1 px-4 py-4">
              {navLinks.map((link) => (
                <a
                  key={link.id}
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  className="rounded-lg px-4 py-3 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                  {t.nav[link.key]}
                </a>
              ))}
              <Link
                to="/login"
                onClick={() => setMobileOpen(false)}
                className="mt-2 rounded-lg border border-[#3B82F6] px-4 py-3 text-center text-[#3B82F6]"
              >
                {t.nav.login}
              </Link>
              <Link
                to="/register"
                onClick={() => setMobileOpen(false)}
                className="rounded-lg bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] px-4 py-3 text-center font-medium text-white"
              >
                {t.nav.getStarted}
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  )
}
