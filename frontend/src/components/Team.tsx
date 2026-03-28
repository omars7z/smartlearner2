import { useRef } from 'react'
import { useInView } from 'framer-motion'
import { motion } from 'framer-motion'
import { Linkedin, GraduationCap, User } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'

const students = [
  {
    key: 'manar' as const,
    /** لا يوجد ملف صورة — يُعرض أيقونة بدل الصورة */
    photo: null as string | null,
    linkedin: 'https://www.linkedin.com/in/manar-al-nashash-a968b7301',
    imgScale: 1.05,
    borderClass: 'border-[#3B82F6]/30',
  },
  {
    key: 'omar' as const,
    photo: '/team/omar.png',
    linkedin: 'https://www.linkedin.com/in/omar-altamimi-3a6883207',
    imgScale: 1.45,
    borderClass: 'border-[#3B82F6]/30',
  },
  {
    key: 'mohammed' as const,
    photo: '/team/mohammed.png',
    linkedin: 'https://www.linkedin.com/in/mohammed-atweh-266265317',
    imgScale: 1.12,
    borderClass: 'border-slate-200 dark:border-slate-600',
  },
] as const

const supervisorLinkedin = 'https://www.linkedin.com/in/rasha-obeidat-39208a90'

const AVATAR_SIZE = 144

export default function Team() {
  const { t } = useLanguage()
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: '-80px' })

  return (
    <section id="team" ref={ref} className="py-24 px-4 bg-white dark:bg-slate-900">
      <div className="max-w-5xl mx-auto">
        <motion.h2
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          className="text-3xl sm:text-4xl font-bold text-center text-slate-900 dark:text-white mb-16"
        >
          {t.team.title}
        </motion.h2>

        <div className="flex flex-col items-center gap-14">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ delay: 0.1 }}
            whileHover={{ y: -6 }}
            className="glass-card rounded-2xl p-8 text-center w-full max-w-sm mx-auto"
          >
            <motion.div
              className="w-20 h-20 mx-auto mb-4 rounded-full bg-gradient-to-br from-amber-500 to-rose-500 flex items-center justify-center flex-shrink-0"
              whileHover={{ scale: 1.05 }}
            >
              <GraduationCap className="h-10 w-10 text-white" />
            </motion.div>
            <h3 className="font-semibold text-slate-900 dark:text-white mb-1">Dr. Rasha Obeidat</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">{t.team.supervisor}</p>
            <a
              href={supervisorLinkedin}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex p-2 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 hover:bg-[#0A66C2] hover:text-white transition-colors"
              aria-label="LinkedIn"
            >
              <Linkedin className="h-5 w-5" />
            </a>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 sm:gap-8 w-full">
            {students.map((s, i) => (
              <motion.div
                key={s.key}
                initial={{ opacity: 0, y: 30 }}
                animate={isInView ? { opacity: 1, y: 0 } : {}}
                transition={{ delay: 0.2 + i * 0.1 }}
                whileHover={{ y: -6 }}
                className="glass-card rounded-2xl p-6 text-center flex flex-col items-center"
              >
                <div
                  className={`rounded-full overflow-hidden flex-shrink-0 border-2 bg-slate-100 dark:bg-slate-800 ${s.borderClass}`}
                  style={{ width: AVATAR_SIZE, height: AVATAR_SIZE }}
                >
                  {s.photo ? (
                    <img
                      src={s.photo}
                      alt={t.team.members[s.key]}
                      width={AVATAR_SIZE}
                      height={AVATAR_SIZE}
                      loading="eager"
                      decoding="async"
                      draggable={false}
                      className="w-full h-full object-cover object-center"
                      style={{ transform: `scale(${s.imgScale})` }}
                    />
                  ) : (
                    <div
                      className="w-full h-full flex items-center justify-center bg-slate-200 dark:bg-slate-700"
                      aria-hidden
                    >
                      <User className="w-16 h-16 text-slate-500 dark:text-slate-400" strokeWidth={1.25} />
                    </div>
                  )}
                </div>
                <h3 className="font-semibold text-slate-900 dark:text-white mt-4 mb-1 text-base">{t.team.members[s.key]}</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">{t.team.student}</p>
                {t.team.bio[s.key] && (
                  <p className="text-xs text-slate-600 dark:text-slate-400 mb-4 line-clamp-4 text-balance leading-relaxed flex-1 min-h-0">
                    {t.team.bio[s.key]}
                  </p>
                )}
                <a
                  href={s.linkedin}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex p-2 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 hover:bg-[#0A66C2] hover:text-white transition-colors mt-auto"
                  aria-label="LinkedIn"
                >
                  <Linkedin className="h-5 w-5" />
                </a>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
