import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { motion } from 'framer-motion'
import { useLanguage } from '../context/LanguageContext'

const techStack = [
  'Python',
  'FastAPI',
  'LangChain',
  'MCP Server',
  'PostgreSQL',
  'Redis',
  'Vector DB',
  'PyTorch (DKT)',
  'React',
]

export default function About() {
  const { t } = useLanguage()
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section id="about" ref={ref} className="py-24 px-4 bg-slate-50 dark:bg-slate-900/50">
      <div className="max-w-6xl mx-auto">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          className="text-3xl sm:text-4xl font-bold text-center text-slate-900 dark:text-white mb-16"
        >
          {t.about.title}
        </motion.h2>

        <div className="grid md:grid-cols-2 gap-12 items-center">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={isInView ? { opacity: 1, x: 0 } : {}}
            transition={{ delay: 0.1 }}
          >
            <p className="text-lg text-slate-600 dark:text-slate-400 leading-relaxed">
              {t.about.desc}
            </p>
          </motion.div>
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            animate={isInView ? { opacity: 1, x: 0 } : {}}
            transition={{ delay: 0.2 }}
            className="flex flex-wrap gap-3 justify-center md:justify-start"
          >
            {techStack.map((tech, i) => (
              <motion.span
                key={tech}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={isInView ? { opacity: 1, scale: 1 } : {}}
                transition={{ delay: 0.3 + i * 0.05 }}
                whileHover={{ scale: 1.05 }}
                className="px-4 py-2 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 font-medium shadow-sm"
              >
                {tech}
              </motion.span>
            ))}
          </motion.div>
        </div>
      </div>
    </section>
  )
}
