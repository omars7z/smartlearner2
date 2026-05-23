import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { flattenLessonsInCourseOrder, normalizeSyllabusModules } from '../utils/syllabusOrder'
import { useLocation, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertCircle, BookOpen, CheckCircle2, ChevronDown, ChevronRight, ClipboardCheck, Lock } from 'lucide-react'
import { useDashboard } from '../context/DashboardContext'
import { useToast } from '../context/ToastContext'
import { useAccentTheme } from '../hooks/useAccentTheme'
import {
  lessonsApi,
  quickAssessmentApi,
  type LessonDto,
  type ModuleDto,
  type StructuredLesson,
  type LessonSection,
  type QuickAssessmentQuestionDto,
} from '../services/api'
import {
  extractCourseIdFromModules,
  moduleProgressStats,
  resolveLessonUiStatus,
  type LessonProgressEntry,
  type LessonUiStatus,
} from '../utils/lessonProgressUi'

function LessonStatusIcon({ status }: { status: LessonUiStatus }) {
  if (status === 'completed') {
    return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" aria-hidden />
  }
  if (status === 'locked') {
    return <Lock className="h-3.5 w-3.5 shrink-0 text-slate-500" aria-hidden />
  }
  if (status === 'failed') {
    return <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-400" aria-hidden />
  }
  return <span className="h-3.5 w-3.5 shrink-0 rounded-full border border-slate-500/60" aria-hidden />
}

export default function DashboardLessons() {
  const { accentPrimary, accentSecondary } = useAccentTheme()
  const {
    syllabusModules,
    currentLesson,
    setCurrentLesson,
    setCurrentTopic,
    placementResult,
    mergeAnalyticsFromQA,
    setSyllabusModules,
  } = useDashboard()
  const { addToast } = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const stateLesson = (location.state as { lesson?: LessonDto })?.lesson
  const [selectedLesson, setSelectedLesson] = useState<LessonDto | null>(stateLesson ?? currentLesson)
  const [lesson, setLesson] = useState<StructuredLesson | null>(null)
  const [contentLoading, setContentLoading] = useState(false)
  const [openExercise, setOpenExercise] = useState<Record<string, boolean>>({})

  const [assessmentLoading, setAssessmentLoading] = useState(false)
  const [assessmentOpen, setAssessmentOpen] = useState(false)
  const [assessmentQuestions, setAssessmentQuestions] = useState<QuickAssessmentQuestionDto[]>([])
  const [assessmentAnswers, setAssessmentAnswers] = useState<Record<string, number>>({})
  const [assessmentSubmitting, setAssessmentSubmitting] = useState(false)
  const [assessmentResult, setAssessmentResult] = useState<{ correct_count: number; total: number } | null>(null)
  const [followUpExplanation, setFollowUpExplanation] = useState<any>(null)
  const [assessmentStatusMessage, setAssessmentStatusMessage] = useState<string | null>(null)
  const [resultModalOpen, setResultModalOpen] = useState(false)
  const [resultModalPassed, setResultModalPassed] = useState(false)
  const [resultModalMessage, setResultModalMessage] = useState('')
  const [resultModalNextLesson, setResultModalNextLesson] = useState<LessonDto | null>(null)
  const [lessonLockMessage, setLessonLockMessage] = useState<string | null>(null)
  const [progressMap, setProgressMap] = useState<Record<string, LessonProgressEntry>>({})
  const [progressSummary, setProgressSummary] = useState({ completed: 0, total: 0, percent: 0 })
  const lessonTopRef = useRef<HTMLDivElement | null>(null)

  const courseId = useMemo(() => extractCourseIdFromModules(syllabusModules), [syllabusModules])

  const refreshProgress = useCallback(async () => {
    if (!courseId) {
      setProgressMap({})
      setProgressSummary({ completed: 0, total: 0, percent: 0 })
      return
    }
    try {
      const data = await lessonsApi.getProgress(courseId)
      setProgressMap(data.lessons ?? {})
      setProgressSummary({
        completed: data.completed_assessable ?? 0,
        total: data.total_assessable ?? 0,
        percent: data.overall_percent ?? 0,
      })
    } catch {
      /* keep last snapshot */
    }
  }, [courseId])

  const selectLesson = useCallback(
    (lesson: LessonDto) => {
      const status = resolveLessonUiStatus(lesson, progressMap)
      if (status === 'locked') {
        addToast('error', 'Complete the previous lesson quiz to unlock this one.')
        return
      }
      setSelectedLesson(lesson)
      setCurrentLesson(lesson)
    },
    [addToast, progressMap, setCurrentLesson],
  )

  const syllabusOrdered = useMemo(() => normalizeSyllabusModules(syllabusModules), [syllabusModules])
  const orderedFlatLessons = useMemo(() => flattenLessonsInCourseOrder(syllabusModules), [syllabusModules])
  const hasSyllabus = syllabusModules.length > 0

  const displayLesson = selectedLesson ?? stateLesson ?? currentLesson
  const resolvedTopic = useMemo(() => {
    if (!displayLesson) return undefined
    return (
      (displayLesson as any).topic ||
      (displayLesson as any).topic_name ||
      displayLesson.title ||
      displayLesson.lesson_id
    )
  }, [displayLesson])

  const level = useMemo(() => {
    const l = (placementResult?.level || '').toLowerCase()
    if (l === 'advanced' || l === 'intermediate' || l === 'beginner') return l
    return 'beginner'
  }, [placementResult?.level])

  useEffect(() => {
    if (resolvedTopic) setCurrentTopic(resolvedTopic)
  }, [resolvedTopic, setCurrentTopic])

  useEffect(() => {
    void refreshProgress()
  }, [refreshProgress, syllabusModules])

  useEffect(() => {
    if (!displayLesson) {
      setLesson(null)
      setLessonLockMessage(null)
      return
    }
    setContentLoading(true)
    setLesson(null)
    setLessonLockMessage(null)
    lessonsApi
      .getLesson(displayLesson.lesson_id, {
        topic: resolvedTopic,
        lessonTitle: displayLesson.title,
        level,
        durationMinutes: (displayLesson as any).duration_minutes ?? 20,
      })
      .then((data) => setLesson(data.lesson))
      .catch((err: unknown) => {
        const status = (err as { response?: { status?: number; data?: { detail?: unknown } } })?.response?.status
        const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
        if (status === 403) {
          const msg =
            typeof detail === 'object' && detail != null && 'error' in detail && typeof (detail as { error?: string }).error === 'string'
              ? (detail as { error: string }).error
              : 'Lesson locked. Complete previous lesson first.'
          setLessonLockMessage(msg)
        }
        setLesson(null)
      })
      .finally(() => setContentLoading(false))
  }, [displayLesson?.lesson_id, displayLesson?.title, resolvedTopic, level])

  useEffect(() => {
    setAssessmentOpen(false)
    setAssessmentQuestions([])
    setAssessmentAnswers({})
    setAssessmentResult(null)
    setFollowUpExplanation(null)
    setAssessmentStatusMessage(null)
    setResultModalOpen(false)
    setResultModalPassed(false)
    setResultModalMessage('')
    setResultModalNextLesson(null)
  }, [displayLesson?.lesson_id])

  const renderSection = (section: LessonSection, idx: number) => {
    if (section.type === 'markdown') {
      return (
        <article
          key={idx}
          className="lesson-markdown text-[color:var(--text-secondary)] leading-relaxed
            [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-[color:var(--text-primary)] [&_h2]:mt-8 [&_h2]:mb-3 [&_h2]:first:mt-0
            [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-[color:var(--text-primary)] [&_h3]:mt-5 [&_h3]:mb-2
            [&_p]:mb-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-3 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-3
            [&_li]:mb-1 [&_strong]:text-[color:var(--text-primary)] [&_code]:text-sky-300 [&_code]:text-[0.9em]
            [&_pre]:rounded-lg [&_pre]:border [&_pre]:p-4 [&_pre]:my-4 [&_pre]:overflow-x-auto [&_pre]:text-sm
            [&_pre]:bg-[#0b1220] [&_pre]:text-slate-200 [&_blockquote]:border-l-4 [&_blockquote]:border-sky-500/40 [&_blockquote]:pl-4 [&_blockquote]:italic"
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              pre: ({ children }) => <pre className="not-prose">{children}</pre>,
            }}
          >
            {section.content}
          </ReactMarkdown>
        </article>
      )
    }
    if (section.type === 'introduction') {
      return (
        <div key={idx} className="rounded-xl p-4 border border-sky-500/20 bg-sky-500/5">
          <p className="text-[color:var(--text-secondary)] leading-relaxed">{section.content}</p>
        </div>
      )
    }
    if (section.type === 'explanation') {
      return (
        <div key={idx} className="mt-6">
          {section.title && (
            <h2 className="text-lg font-semibold text-[color:var(--text-primary)] mb-2">{section.title}</h2>
          )}
          <p className="text-[color:var(--text-secondary)] leading-relaxed whitespace-pre-wrap">{section.content}</p>
        </div>
      )
    }
    if (section.type === 'code_example') {
      return (
        <div key={idx} className="mt-6">
          {section.title && (
            <h3 className="text-base font-semibold text-[color:var(--text-primary)] mb-2">{section.title}</h3>
          )}
          <div className="rounded-xl overflow-hidden border" style={{ borderColor: 'var(--border-color)' }}>
            <pre className="p-4 text-sm overflow-x-auto" style={{ backgroundColor: '#0b1220', color: '#e5e7eb' }}>
              <code>{section.code}</code>
            </pre>
          </div>
          {section.explanation && (
            <p className="text-sm text-[color:var(--text-muted)] mt-2 whitespace-pre-wrap">{section.explanation}</p>
          )}
        </div>
      )
    }
    if (section.type === 'common_mistakes') {
      return (
        <div key={idx} className="mt-6">
          <h3 className="text-base font-semibold text-[color:var(--text-primary)] mb-3">Common mistakes</h3>
          <div className="space-y-3">
            {section.mistakes?.map((m, mi) => (
              <div key={mi} className="rounded-xl border p-4" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}>
                <p className="text-sm font-medium text-[color:var(--text-primary)] mb-3">{m.description}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 overflow-hidden">
                    <div className="px-3 py-2 text-xs font-semibold text-rose-300 border-b border-rose-500/20">Wrong</div>
                    <pre className="p-3 text-xs overflow-x-auto" style={{ backgroundColor: '#120a0a', color: '#fecaca' }}>
                      <code>{m.wrong_code}</code>
                    </pre>
                  </div>
                  <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 overflow-hidden">
                    <div className="px-3 py-2 text-xs font-semibold text-emerald-300 border-b border-emerald-500/20">Correct</div>
                    <pre className="p-3 text-xs overflow-x-auto" style={{ backgroundColor: '#07150f', color: '#bbf7d0' }}>
                      <code>{m.correct_code}</code>
                    </pre>
                  </div>
                </div>
                {m.explanation && (
                  <p className="text-xs text-[color:var(--text-muted)] mt-2 whitespace-pre-wrap">{m.explanation}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )
    }
    if (section.type === 'exercises') {
      return (
        <div key={idx} className="mt-6">
          <h3 className="text-base font-semibold text-[color:var(--text-primary)] mb-3">Practice exercises</h3>
          <div className="space-y-3">
            {section.exercises?.map((ex, ei) => {
              const key = `${idx}-${ei}`
              const open = !!openExercise[key]
              return (
                <div key={ei} className="rounded-xl border overflow-hidden" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}>
                  <button
                    type="button"
                    onClick={() => setOpenExercise((p) => ({ ...p, [key]: !open }))}
                    className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-white/5"
                  >
                    <div>
                      <p className="text-sm font-semibold text-[color:var(--text-primary)]">{ex.title}</p>
                      <span className="text-[10px] text-[color:var(--text-muted)] uppercase">{ex.difficulty}</span>
                    </div>
                    {open ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
                  </button>
                  <div className="px-4 pb-4">
                    <p className="text-sm text-[color:var(--text-secondary)] whitespace-pre-wrap">{ex.description}</p>
                    <div className="mt-3">
                      <button
                        type="button"
                        onClick={() => setOpenExercise((p) => ({ ...p, [key]: true }))}
                        className="text-xs font-semibold text-white rounded-lg px-3 py-2"
                        style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
                      >
                        Show solution
                      </button>
                      {open && (
                        <pre className="mt-3 p-3 rounded-lg text-xs overflow-x-auto" style={{ backgroundColor: '#0b1220', color: '#e5e7eb' }}>
                          <code>{ex.solution}</code>
                        </pre>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )
    }
    if (section.type === 'summary') {
      return (
        <div key={idx} className="mt-6 rounded-xl border p-4" style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}>
          <h3 className="text-base font-semibold text-[color:var(--text-primary)] mb-2">Summary</h3>
          <ul className="list-disc pl-5 space-y-1 text-sm text-[color:var(--text-secondary)]">
            {section.points?.map((p, pi) => (
              <li key={pi}>{p}</li>
            ))}
          </ul>
        </div>
      )
    }
    return null
  }

  return (
    <div
      className="flex-1 min-w-0 flex overflow-hidden"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <aside
        className="w-64 shrink-0 border-r overflow-y-auto p-4"
        style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
      >
        <h2 className="text-sm font-semibold text-[color:var(--text-primary)] mb-2">Lessons</h2>
        {hasSyllabus && progressSummary.total > 0 ? (
          <div className="mb-4">
            <div className="flex items-center justify-between text-[10px] text-[color:var(--text-muted)] mb-1">
              <span>Course progress</span>
              <span>
                {progressSummary.completed}/{progressSummary.total}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${Math.min(100, progressSummary.percent)}%` }}
              />
            </div>
          </div>
        ) : null}
        {!hasSyllabus ? (
          <p className="text-xs text-[color:var(--text-muted)]">
            Generate your syllabus first to see lessons.
          </p>
        ) : syllabusModules.length === 0 ? (
          <p className="text-xs text-[color:var(--text-muted)]">No lessons in syllabus.</p>
        ) : (
          <div className="space-y-4">
            {syllabusOrdered.map((mod) => {
              const modStats = moduleProgressStats(mod, progressMap)
              return (
              <div key={mod.module_id}>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-muted)] truncate">
                    {mod.title}
                  </p>
                  {modStats.total > 0 ? (
                    <span className="text-[10px] text-emerald-400/90 shrink-0">
                      {modStats.done}/{modStats.total}
                    </span>
                  ) : null}
                </div>
                {modStats.total > 0 ? (
                  <div className="h-1 rounded-full bg-white/5 overflow-hidden mb-2">
                    <div
                      className="h-full rounded-full bg-emerald-500/70"
                      style={{ width: `${Math.round((modStats.done / modStats.total) * 100)}%` }}
                    />
                  </div>
                ) : null}
                <ul className="space-y-1">
                  {(mod.lessons || []).map((lesson) => {
                    const subActive = lesson.sub_lessons?.some((s) => s.lesson_id === displayLesson?.lesson_id)
                    const active = displayLesson?.lesson_id === lesson.lesson_id || subActive
                    const rootStatus = resolveLessonUiStatus(lesson, progressMap)
                    const rootLocked = rootStatus === 'locked'
                    return (
                      <li key={lesson.lesson_id}>
                        <button
                          type="button"
                          onClick={() => selectLesson(lesson)}
                          disabled={rootLocked}
                          className={`w-full text-left rounded-lg px-3 py-2 text-xs transition-colors flex items-start gap-2 ${
                            active
                              ? 'text-white'
                              : rootStatus === 'completed'
                                ? 'text-emerald-200/90 bg-emerald-500/10 border border-emerald-500/20'
                                : rootStatus === 'failed'
                                  ? 'text-amber-200/90 bg-amber-500/10 border border-amber-500/20'
                                  : rootLocked
                                    ? 'text-slate-500 cursor-not-allowed opacity-70'
                                    : 'text-[color:var(--text-secondary)] hover:bg-white/10 border border-transparent'
                          }`}
                          style={
                            active
                              ? {
                                  background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
                                }
                              : undefined
                          }
                        >
                          <LessonStatusIcon status={rootStatus} />
                          <span className="min-w-0 flex-1">
                            <span className="font-medium leading-snug block truncate" title={lesson.title}>
                              {lesson.title}
                            </span>
                            {lesson.sub_lessons?.length ? (
                              <span className="text-[10px] opacity-80 mt-0.5 block">
                                {lesson.sub_lessons.length} parts
                              </span>
                            ) : null}
                          </span>
                        </button>
                        {lesson.sub_lessons?.length ? (
                          <ul className="mt-1 ml-2 space-y-0.5 border-l border-white/10 pl-2">
                            {lesson.sub_lessons.map((sub, si) => {
                              const subStatus = resolveLessonUiStatus(sub, progressMap)
                              const subLocked = subStatus === 'locked'
                              return (
                              <li key={sub.lesson_id}>
                                <button
                                  type="button"
                                  onClick={() => selectLesson(sub)}
                                  disabled={subLocked}
                                  className={`w-full text-left rounded-md px-2 py-1.5 text-[11px] transition-colors flex items-start gap-1.5 ${
                                    displayLesson?.lesson_id === sub.lesson_id
                                      ? 'text-sky-200 bg-white/10'
                                      : subStatus === 'completed'
                                        ? 'text-emerald-300/90 bg-emerald-500/10'
                                        : subStatus === 'failed'
                                          ? 'text-amber-300/90 bg-amber-500/10'
                                          : subLocked
                                            ? 'text-slate-600 cursor-not-allowed opacity-70'
                                            : 'text-[color:var(--text-muted)] hover:bg-white/5'
                                  }`}
                                >
                                  <LessonStatusIcon status={subStatus} />
                                  <span className="min-w-0 flex-1">
                                    <span className="text-sky-400/90 font-medium">Part {si + 1}</span>
                                    {sub.is_final_sub_lesson ? (
                                      <span className="ml-1 text-[9px] font-semibold text-emerald-300/90">· quiz</span>
                                    ) : null}
                                    <span className="block truncate opacity-90" title={sub.title}>
                                      {sub.title.replace(/^\(part\s+\d+\/\d+\)\s*/i, '').trim() || sub.title}
                                    </span>
                                  </span>
                                </button>
                              </li>
                            )})}
                          </ul>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              </div>
            )})}
          </div>
        )}
        {hasSyllabus && (
          <button
            type="button"
            onClick={() => navigate('/dashboard/syllabus')}
            className="mt-4 w-full rounded-lg py-2 text-xs font-medium text-[color:var(--text-muted)] hover:bg-white/10"
          >
            Back to Syllabus
          </button>
        )}
      </aside>

      <div className="flex-1 min-w-0 overflow-y-auto p-6">
        {!displayLesson ? (
          <div className="flex flex-col items-center justify-center min-h-[300px] text-center">
            <BookOpen className="h-16 w-16 text-slate-600 mb-4" />
            <p className="text-[color:var(--text-secondary)] mb-4">
              {hasSyllabus
                ? 'Select a lesson from the list to start learning.'
                : 'Generate your syllabus first to unlock lessons.'}
            </p>
            {!hasSyllabus && (
              <button
                type="button"
                onClick={() => navigate('/dashboard/syllabus')}
                className="rounded-xl py-2.5 px-4 text-sm font-semibold text-white"
                style={{
                  background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})`,
                }}
              >
                Go to Syllabus
              </button>
            )}
          </div>
        ) : (
          <div className="max-w-3xl">
            <span className="text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-300">
              {resolvedTopic ?? 'Lesson'}
            </span>
            <div className="flex flex-wrap items-center gap-2 mt-2 mb-4">
              <h1 className="text-2xl font-bold text-[color:var(--text-primary)] flex-1 min-w-0 break-words">
                {displayLesson.title}
              </h1>
              {displayLesson.is_sub_lesson ? (
                <span className="text-[10px] shrink-0 px-2 py-0.5 rounded bg-amber-500/20 text-amber-200 border border-amber-500/30">
                  Focused part
                </span>
              ) : null}
            </div>
            <div
              ref={lessonTopRef}
              className="rounded-xl p-6"
              style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
            >
              {contentLoading ? (
                <p className="text-[color:var(--text-muted)]">Loading content…</p>
              ) : lessonLockMessage ? (
                <p className="text-sm text-amber-300 leading-relaxed">{lessonLockMessage}</p>
              ) : lesson ? (
                <>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] text-[color:var(--text-muted)]">
                      ~{lesson.duration_minutes} min read · Level: {level}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-700 text-slate-300">
                      {lesson.is_parent_with_sub_lessons ? 'Topic overview' : 'Lesson'}
                    </span>
                  </div>
                  {lesson.sections?.map(renderSection)}

                  {lesson.sub_lessons?.length ? (
                    <div
                      className="mt-8 rounded-xl border p-5"
                      style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
                    >
                      <h3 className="text-sm font-semibold text-[color:var(--text-primary)] mb-3">Parts in this topic</h3>
                      <p className="text-xs text-[color:var(--text-muted)] mb-3">
                        Read in any order. Only the <strong>final</strong> part includes the topic quiz that unlocks the next lesson.
                      </p>
                      <div className="flex flex-col gap-2">
                        {lesson.sub_lessons.map((sub, si) => (
                          <button
                            key={sub.lesson_id}
                            type="button"
                            onClick={() => selectLesson(sub)}
                            className="text-left rounded-lg px-3 py-2 text-xs border border-sky-500/30 bg-sky-500/5 hover:bg-sky-500/10 text-[color:var(--text-primary)]"
                          >
                            <span className="font-semibold text-sky-300">Part {si + 1}</span>
                            {sub.is_final_sub_lesson ? (
                              <span className="ml-1 text-[10px] font-semibold text-emerald-300">· topic quiz</span>
                            ) : null}
                            <span className="block text-[color:var(--text-secondary)] mt-0.5">{sub.title}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div
                    className="mt-8 rounded-xl border p-5"
                    style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <ClipboardCheck className="h-5 w-5 text-sky-400" />
                      <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                        Quick Assessment (5 questions)
                      </h2>
                    </div>

                    {lesson.is_parent_with_sub_lessons ? (
                      <p className="text-sm text-[color:var(--text-secondary)]">
                        This overview has no quiz. Open the <strong>final</strong> part under this topic to take the one
                        assessment that unlocks the next lesson.
                      </p>
                    ) : displayLesson?.is_sub_lesson && lesson?.is_final_sub_lesson === false ? (
                      <p className="text-sm text-[color:var(--text-secondary)]">
                        This part is reading only. Open the <strong>final</strong> part of this topic (see sidebar) to
                        take the quiz and continue the course.
                      </p>
                    ) : !assessmentOpen ? (
                      <button
                        type="button"
                        onClick={async () => {
                          if (!displayLesson) return
                          if (!resolvedTopic) return
                          setAssessmentLoading(true)
                          setAssessmentOpen(false)
                          setAssessmentQuestions([])
                          setAssessmentAnswers({})
                          setAssessmentResult(null)
                          setFollowUpExplanation(null)
                          try {
                            const resp = await quickAssessmentApi.generate(displayLesson.lesson_id, resolvedTopic, level)
                            setAssessmentQuestions(resp.questions || [])
                            setAssessmentOpen(true)
                          } catch (err) {
                            // eslint-disable-next-line no-console
                            console.error(err)
                            setAssessmentOpen(false)
                          } finally {
                            setAssessmentLoading(false)
                          }
                        }}
                        disabled={assessmentLoading || !resolvedTopic}
                        className="rounded-xl px-4 py-3 text-white font-semibold"
                        style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
                      >
                        {assessmentLoading ? 'Generating...' : 'Complete lesson and start assessment'}
                      </button>
                    ) : (
                      <>
                        <div className="space-y-4">
                          {assessmentQuestions.map((q, i) => (
                            <div
                              key={q.id}
                              className="rounded-lg border p-4"
                              style={{ borderColor: 'var(--border-color)', backgroundColor: 'rgba(15,23,42,0.2)' }}
                            >
                              <p className="text-xs text-[color:var(--text-muted)] mb-2">Question {i + 1}</p>
                              <p className="text-sm font-medium text-[color:var(--text-primary)] mb-3">{q.text}</p>
                              <div className="space-y-2">
                                {q.options.map((opt, oi) => {
                                  const selected = assessmentAnswers[q.id] === oi
                                  return (
                                    <button
                                      key={oi}
                                      type="button"
                                      onClick={() => setAssessmentAnswers((p) => ({ ...p, [q.id]: oi }))}
                                      className="w-full text-left rounded-lg px-3 py-2 text-sm border"
                                      style={{
                                        borderColor: selected ? 'rgba(59,130,246,0.9)' : 'var(--border-color)',
                                        backgroundColor: selected ? 'rgba(59,130,246,0.15)' : 'transparent',
                                      }}
                                    >
                                      {String.fromCharCode(65 + oi)}. {opt}
                                    </button>
                                  )
                                })}
                              </div>
                            </div>
                          ))}
                        </div>

                        <div className="mt-5 flex items-center gap-3">
                          <button
                            type="button"
                            onClick={async () => {
                              if (!displayLesson || !resolvedTopic) return
                              setAssessmentSubmitting(true)
                              setAssessmentResult(null)
                              setFollowUpExplanation(null)
                              setAssessmentStatusMessage(null)
                              try {
                                const answers = assessmentQuestions.map((q) => ({
                                  question_id: q.id,
                                  answer_index: assessmentAnswers[q.id],
                                }))
                                const resp = await quickAssessmentApi.grade(displayLesson.lesson_id, resolvedTopic, answers as any)
                                mergeAnalyticsFromQA(resp.analytics)
                                void refreshProgress()
                                setAssessmentResult(
                                  resp.grading
                                    ? { correct_count: resp.grading.correct_count, total: resp.grading.total }
                                    : null
                                )
                                setFollowUpExplanation(resp.follow_up_explanation ?? null)
                                const followup: any = resp.follow_up_explanation ?? null
                                if (followup?.explanation?.core_explanation) {
                                  setAssessmentStatusMessage(String(followup.explanation.core_explanation))
                                }

                                if (resp.next_action === 'advance_to_next_lesson') {
                                  const idx = orderedFlatLessons.findIndex(
                                    (x) => x.lesson.lesson_id === displayLesson.lesson_id,
                                  )
                                  const next = idx >= 0 ? orderedFlatLessons[idx + 1] : null
                                  setResultModalPassed(true)
                                  setResultModalNextLesson(next?.lesson ?? null)
                                  setResultModalMessage(
                                    followup?.explanation?.core_explanation
                                      ? String(followup.explanation.core_explanation)
                                      : 'Great job! You passed the assessment.'
                                  )
                                  setResultModalOpen(true)
                                } else if (resp.next_action === 'go_to_sub_lessons') {
                                  const mods = resp.updated_syllabus_modules
                                  if (mods?.length) {
                                    setSyllabusModules(mods as ModuleDto[])
                                    const pid = displayLesson.lesson_id
                                    outer: for (const mod of mods) {
                                      for (const les of mod.lessons || []) {
                                        if (les.lesson_id === pid && les.sub_lessons?.length) {
                                          const first = les.sub_lessons[0]
                                          selectLesson(first)
                                          break outer
                                        }
                                      }
                                    }
                                  }
                                  setAssessmentOpen(false)
                                  setAssessmentQuestions([])
                                  setAssessmentAnswers({})
                                  setResultModalPassed(false)
                                  setResultModalMessage(
                                    followup?.explanation?.core_explanation
                                      ? String(followup.explanation.core_explanation)
                                      : 'This topic was split into parts. Read them in any order; take the quiz on the final part to continue.'
                                  )
                                  setResultModalOpen(true)
                                } else if (resp.next_action === 'retry_after_regeneration') {
                                  // The backend regenerated lesson content; reload it immediately.
                                  setContentLoading(true)
                                  try {
                                    const refreshed = await lessonsApi.getLesson(displayLesson.lesson_id, {
                                      topic: resolvedTopic,
                                      lessonTitle: displayLesson.title,
                                      level,
                                      durationMinutes: (displayLesson as any).duration_minutes ?? 20,
                                    })
                                    setLesson(refreshed.lesson)
                                    // Load the freshly regenerated 5-question set from updated lesson content.
                                    const regenerated = await quickAssessmentApi.generate(
                                      displayLesson.lesson_id,
                                      resolvedTopic,
                                      level,
                                    )
                                    setAssessmentQuestions(regenerated.questions || [])
                                    setAssessmentAnswers({})
                                  } catch {
                                    // keep current lesson view if refresh fails
                                  } finally {
                                    setContentLoading(false)
                                  }
                                  setResultModalPassed(false)
                                  setResultModalMessage(
                                    followup?.explanation?.core_explanation
                                      ? String(followup.explanation.core_explanation)
                                      : 'You did not pass. The lesson has been regenerated to be easier. Review it from the start.'
                                  )
                                  setResultModalOpen(true)
                                } else if (resp.next_action === 'review_required_locked') {
                                  setResultModalPassed(false)
                                  setResultModalMessage(
                                    followup?.explanation?.core_explanation
                                      ? String(followup.explanation.core_explanation)
                                      : 'Maximum attempts reached. Please review the lesson from the start before retrying.'
                                  )
                                  setResultModalOpen(true)
                                }
                              } catch (err) {
                                // eslint-disable-next-line no-console
                                console.error(err)
                                setAssessmentStatusMessage('Could not submit assessment. Please try again.')
                              } finally {
                                setAssessmentSubmitting(false)
                              }
                            }}
                            disabled={assessmentSubmitting || assessmentQuestions.some((q) => assessmentAnswers[q.id] == null)}
                            className="rounded-xl px-4 py-3 text-white font-semibold"
                            style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
                          >
                            {assessmentSubmitting ? 'Checking...' : 'Submit answers'}
                          </button>
                        </div>

                        {assessmentResult && assessmentResult.total > 0 && (
                          <div className="mt-4 text-sm" style={{ color: 'var(--text-primary)' }}>
                            Score: {assessmentResult.correct_count}/{assessmentResult.total}
                          </div>
                        )}

                        {assessmentStatusMessage && (
                          <div className="mt-3 text-sm text-amber-300 whitespace-pre-wrap">
                            {assessmentStatusMessage}
                          </div>
                        )}

                        {followUpExplanation?.explanation?.core_explanation && (
                          <div
                            className="mt-4 rounded-xl border p-4"
                            style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
                          >
                            <h3 className="text-sm font-semibold text-[color:var(--text-primary)] mb-2">Alternative explanation</h3>
                            <p className="text-[color:var(--text-secondary)] whitespace-pre-wrap">{followUpExplanation.explanation.core_explanation}</p>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-[color:var(--text-muted)]">
                  Could not load structured content for this lesson yet.
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      {resultModalOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4">
          <div
            className="w-full max-w-md rounded-2xl border p-5"
            style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
          >
            <h3 className="text-lg font-semibold text-[color:var(--text-primary)] mb-2">
              {resultModalPassed ? 'Assessment Passed' : 'Assessment Result'}
            </h3>
            {assessmentResult && (
              <p className="text-sm mb-2 text-[color:var(--text-primary)]">
                Grade: {assessmentResult.correct_count}/{assessmentResult.total}
              </p>
            )}
            <p className="text-sm whitespace-pre-wrap text-[color:var(--text-secondary)] mb-4">
              {resultModalMessage}
            </p>

            <div className="flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setResultModalOpen(false)}
                className="rounded-xl px-3 py-2 text-sm border"
                style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
              >
                Close
              </button>

              {resultModalPassed ? (
                <button
                  type="button"
                  onClick={() => {
                    if (resultModalNextLesson) {
                      selectLesson(resultModalNextLesson)
                      setCurrentTopic((resultModalNextLesson as any).topic || resultModalNextLesson.lesson_id)
                      setAssessmentOpen(false)
                    }
                    void refreshProgress()
                    setResultModalOpen(false)
                  }}
                  className="rounded-xl px-3 py-2 text-sm font-semibold text-white"
                  style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
                >
                  Go to next lesson
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setAssessmentOpen(false)
                    setAssessmentQuestions([])
                    setAssessmentAnswers({})
                    setResultModalOpen(false)
                    lessonTopRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                  }}
                  className="rounded-xl px-3 py-2 text-sm font-semibold text-white"
                  style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
                >
                  Continue
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
