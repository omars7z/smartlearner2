import { useRef, useState, useEffect } from 'react'
import { useInView } from 'framer-motion'
import { motion } from 'framer-motion'
import { Bot, Layers, Zap, BarChart3 } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'

const stats = [
  { key: 'agents' as const, value: 9, suffix: '+', Icon: Bot },
  { key: 'phases' as const, value: 8, suffix: '', Icon: Layers },
  { key: 'adaptive' as const, value: 100, suffix: '%', Icon: Zap },
  { key: 'tracking' as const, value: 24, suffix: '/7', Icon: BarChart3 },
] as const

function AnimatedCounter({ target, suffix = '', inView }: { target: number; suffix?: string; inView: boolean }) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!inView) return
    const duration = 2000
    const step = target / (duration / 16)
    let current = 0
    const timer = setInterval(() => {
      current += step
      if (current >= target) {
        setCount(target)
        clearInterval(timer)
      } else {
        setCount(Math.floor(current))
      }
    }, 16)
    return () => clearInterval(timer)
  }, [target, inView])

  return (
    <span>
      {count}
      {suffix}
    </span>
  )
}

export default function Stats() {
  const { t } = useLanguage()
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })

  return (
    <section ref={ref} className="py-24 px-4 bg-[#0F172A] relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-to-br from-[#3B82F6]/20 to-[#06B6D4]/20" />
      <div className="absolute top-0 left-1/4 w-96 h-96 rounded-full bg-[#3B82F6]/10 blur-3xl" />
      <div className="absolute bottom-0 right-1/4 w-96 h-96 rounded-full bg-[#06B6D4]/10 blur-3xl" />

      <div className="relative max-w-5xl mx-auto">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
          {stats.map((stat, i) => (
            <motion.div
              key={stat.key}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: i * 0.1 }}
              className="text-center"
            >
              <motion.div
                whileHover={{ scale: 1.1 }}
                className="inline-flex rounded-xl bg-white/10 p-4 text-[#06B6D4] mb-4"
              >
                <stat.Icon className="h-10 w-10" />
              </motion.div>
              <div className="text-4xl sm:text-5xl font-bold text-white mb-2">
                <AnimatedCounter target={stat.value} suffix={stat.suffix} inView={isInView} />
              </div>
              <p className="text-slate-300 text-sm sm:text-base">{t.stats[stat.key]}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
