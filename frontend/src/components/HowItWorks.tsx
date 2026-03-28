import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { motion } from 'framer-motion'
import {
  ClipboardList,
  Map,
  BookOpen,
  MessageCircle,
  GraduationCap,
  TrendingUp,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'

const steps = [
  { key: 's1' as const, Icon: ClipboardList },
  { key: 's2' as const, Icon: Map },
  { key: 's3' as const, Icon: BookOpen },
  { key: 's4' as const, Icon: MessageCircle },
  { key: 's5' as const, Icon: GraduationCap },
  { key: 's6' as const, Icon: TrendingUp },
] as const

export default function HowItWorks() {
  const { t } = useLanguage()
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section id="how-it-works" ref={ref} className="py-24 px-4 bg-slate-50 dark:bg-slate-900/50">
      <div className="max-w-3xl mx-auto">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          className="text-3xl sm:text-4xl font-bold text-center text-slate-900 dark:text-white mb-16"
        >
          {t.howItWorks.title}
        </motion.h2>

        <div className="space-y-0">
          {steps.map((step, i) => (
            <motion.div
              key={step.key}
              initial={{ opacity: 0, x: i % 2 === 0 ? -40 : 40 }}
              animate={isInView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: i * 0.15 }}
              className="relative flex gap-6 pb-12 last:pb-0"
            >
              {i < steps.length - 1 && (
                <div className="absolute top-14 start-8 w-0.5 h-[calc(100%-2rem)] bg-gradient-to-b from-[#3B82F6] to-[#06B6D4] opacity-60" />
              )}
              <motion.div
                whileHover={{ scale: 1.1 }}
                className="relative z-10 flex-shrink-0 w-16 h-16 rounded-xl bg-gradient-to-br from-[#3B82F6] to-[#06B6D4] flex items-center justify-center text-white shadow-lg"
              >
                <step.Icon className="h-8 w-8" />
                <span className="absolute -top-1 -end-1 w-6 h-6 rounded-full bg-white dark:bg-slate-800 text-xs font-bold text-[#3B82F6] flex items-center justify-center">
                  {i + 1}
                </span>
              </motion.div>
              <div className="flex-1 pt-1">
                <h3 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">
                  {t.howItWorks.steps[step.key].title}
                </h3>
                <p className="text-slate-600 dark:text-slate-400">
                  {t.howItWorks.steps[step.key].desc}
                </p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
