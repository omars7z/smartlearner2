import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { motion } from 'framer-motion'
import {
  Bot,
  FileCheck,
  Search,
  MessageSquare,
  ClipboardCheck,
  FileQuestion,
  BarChart3,
  Cpu,
} from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import MCPDiagram from './MCPDiagram'

const agents = [
  { key: 'placement' as const, Icon: Bot, color: 'from-blue-500 to-blue-600', glow: 'shadow-blue-500/50' },
  { key: 'syllabusGen' as const, Icon: FileCheck, color: 'from-cyan-500 to-cyan-600', glow: 'shadow-cyan-500/50' },
  { key: 'syllabusVal' as const, Icon: ClipboardCheck, color: 'from-violet-500 to-violet-600', glow: 'shadow-violet-500/50' },
  { key: 'rag' as const, Icon: Search, color: 'from-emerald-500 to-emerald-600', glow: 'shadow-emerald-500/50' },
  { key: 'explanation' as const, Icon: MessageSquare, color: 'from-amber-500 to-amber-600', glow: 'shadow-amber-500/50' },
  { key: 'explanationVal' as const, Icon: ClipboardCheck, color: 'from-rose-500 to-rose-600', glow: 'shadow-rose-500/50' },
  { key: 'exam' as const, Icon: FileQuestion, color: 'from-indigo-500 to-indigo-600', glow: 'shadow-indigo-500/50' },
  { key: 'analytics' as const, Icon: BarChart3, color: 'from-teal-500 to-teal-600', glow: 'shadow-teal-500/50' },
  { key: 'mcp' as const, Icon: Cpu, color: 'from-[#3B82F6] to-[#06B6D4]', glow: 'shadow-blue-500/50' },
] as const

export default function Agents() {
  const { t } = useLanguage()
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section id="agents" ref={ref} className="py-24 px-4 bg-white dark:bg-slate-900">
      <div className="max-w-6xl mx-auto">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          className="text-3xl sm:text-4xl font-bold text-center text-slate-900 dark:text-white mb-8"
        >
          {t.agents.title}
        </motion.h2>

        <MCPDiagram />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mt-12">
          {agents.map((agent, i) => (
            <motion.div
              key={agent.key}
              initial={{ opacity: 0, y: 30 }}
              animate={isInView ? { opacity: 1, y: 0 } : {}}
              transition={{ delay: 0.2 + i * 0.05 }}
              whileHover={{ scale: 1.03, y: -4 }}
              className="glass-card rounded-2xl p-6 relative overflow-hidden group"
            >
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="absolute top-3 end-3 px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-medium"
              >
                Active
              </motion.span>
              <motion.div
                whileHover={{ scale: 1.1 }}
                className={`mb-4 inline-flex rounded-xl bg-gradient-to-br ${agent.color} p-3 text-white shadow-lg ${agent.glow}`}
              >
                <agent.Icon className="h-8 w-8" />
              </motion.div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-1">
                {t.agents[agent.key].name}
              </h3>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                {t.agents[agent.key].role}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}
