import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Play, ChevronDown, CheckCircle2 } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'

const floatingCards = [
  { key: 'placementTest', icon: CheckCircle2 },
  { key: 'aiSyllabus', icon: CheckCircle2 },
  { key: 'smartQA', icon: CheckCircle2 },
  { key: 'performanceAnalytics', icon: CheckCircle2 },
] as const

export default function Hero() {
  const { t } = useLanguage()

  return (
    <section className="relative min-h-screen overflow-hidden flex flex-col items-center justify-center px-4 pt-20 pb-16">
      {/* Animated gradient background */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#0F172A] via-[#1e3a5f] to-[#0F172A] dark:from-[#0F172A] dark:via-[#1e3a5f] dark:to-[#0F172A]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_30%_20%,rgba(59,130,246,0.2)_0%,transparent_50%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_70%_80%,rgba(6,182,212,0.15)_0%,transparent_50%)]" />
      {/* Floating orbs */}
      <div className="absolute top-1/4 left-1/4 w-64 h-64 rounded-full bg-[#3B82F6]/20 blur-3xl animate-pulse" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full bg-[#06B6D4]/15 blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />

      <div className="relative z-10 max-w-4xl mx-auto text-center">
        <motion.h1
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6 }}
          className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white mb-6"
        >
          {t.hero.headline}
        </motion.h1>
        <motion.p
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="text-lg sm:text-xl text-slate-300 max-w-2xl mx-auto mb-10"
        >
          {t.hero.subtitle}
        </motion.p>

        <motion.div
          initial={{ y: 20, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="flex flex-wrap justify-center gap-4 mb-16"
        >
          <Link
            to="/register"
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] px-6 py-3.5 text-lg font-semibold text-white shadow-xl shadow-blue-500/30 hover:shadow-blue-500/50 hover:scale-105 transition-all"
          >
            {t.hero.startLearning}
          </Link>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-xl border border-white/30 px-6 py-3.5 text-lg font-semibold text-white hover:bg-white/10 transition-colors"
          >
            <Play className="h-5 w-5" />
            {t.hero.watchDemo}
          </button>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="flex flex-wrap justify-center gap-4 sm:gap-6"
        >
          {floatingCards.map((card, i) => (
            <motion.div
              key={card.key}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.5 + i * 0.1 }}
              whileHover={{ scale: 1.05, y: -4 }}
              className="flex items-center gap-2 rounded-xl backdrop-blur-xl bg-white/10 border border-white/20 px-4 py-2.5 text-white"
            >
              <card.icon className="h-5 w-5 text-[#06B6D4]" />
              <span className="text-sm font-medium">{t.hero[card.key]}</span>
            </motion.div>
          ))}
        </motion.div>

      </div>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1 }}
        className="absolute bottom-8 left-1/2 -translate-x-1/2"
      >
        <motion.a
          href="#features"
          animate={{ y: [0, 8, 0] }}
          transition={{ repeat: Infinity, duration: 2 }}
          className="inline-flex rounded-full p-2 text-white/80 hover:text-white"
        >
          <ChevronDown className="h-8 w-8" />
        </motion.a>
      </motion.div>
    </section>
  )
}
