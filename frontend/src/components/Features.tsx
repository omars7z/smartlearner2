import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { motion } from 'framer-motion'
import {
  Target,
  BookOpen,
  Bot,
  Search,
  BarChart3,
  ShieldCheck,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'

const featureList = [
  { key: 'placement' as const, Icon: Target, color: 'text-blue-500' },
  { key: 'syllabus' as const, Icon: BookOpen, color: 'text-cyan-500' },
  { key: 'multiAgent' as const, Icon: Bot, color: 'text-violet-500' },
  { key: 'rag' as const, Icon: Search, color: 'text-emerald-500' },
  { key: 'analytics' as const, Icon: BarChart3, color: 'text-amber-500' },
  { key: 'validation' as const, Icon: ShieldCheck, color: 'text-rose-500' },
] as const

export default function Features() {
  const { t } = useLanguage()
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })

  return (
    <section id="features" ref={ref} className="py-24 px-4 bg-slate-50 dark:bg-slate-900/50">
      <div className="max-w-6xl mx-auto">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          className="text-3xl sm:text-4xl font-bold text-center text-slate-900 dark:text-white mb-16"
        >
          {t.features.title}
        </motion.h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {featureList.map((item, i) => (
            <motion.div
              key={item.key}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: i * 0.1 }}
              whileHover={{ scale: 1.02, y: -4 }}
              className="glass-card rounded-2xl p-6 shadow-lg hover:shadow-xl transition-shadow"
            >
              <motion.div
                whileHover={{ scale: 1.1 }}
                className={`mb-4 inline-flex rounded-xl bg-slate-100 dark:bg-slate-800 p-3 ${item.color}`}
              >
                <item.Icon className="h-8 w-8" />
              </motion.div>
              <h3 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">
                {t.features.items[item.key].title}
              </h3>
              <p className="text-slate-600 dark:text-slate-400">
                {t.features.items[item.key].desc}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
