import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BookOpen, ChevronDown, ChevronRight, ClipboardCheck } from 'lucide-react'
import { useDashboard } from '../context/DashboardContext'
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

export default function DashboardLessons() {
  const { accentPrimary, accentSecondary } = useAccentTheme()
  const { syllabusModules, currentLesson, setCurrentLesson, setCurrentTopic, placementResult, mergeAnalyticsFromQA } = useDashboard()
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

  const allLessons: { lesson: LessonDto; module: ModuleDto }[] = []
  syllabusModules.forEach((mod) => {
    if (mod.lessons) {
      mod.lessons.forEach((l) => allLessons.push({ lesson: l, module: mod }))
    }
  })
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
    if (!displayLesson) {
      setLesson(null)
      return
    }
    setContentLoading(true)
    setLesson(null)
    lessonsApi
      .getLesson(displayLesson.lesson_id, {
        topic: resolvedTopic,
        lessonTitle: displayLesson.title,
        level,
        durationMinutes: (displayLesson as any).duration_minutes ?? 20,
      })
      .then((data) => setLesson(data.lesson))
      .catch(() => setLesson(null))
      .finally(() => setContentLoading(false))
  }, [displayLesson?.lesson_id, displayLesson?.title, resolvedTopic, level])

  useEffect(() => {
    setAssessmentOpen(false)
    setAssessmentQuestions([])
    setAssessmentAnswers({})
    setAssessmentResult(null)
    setFollowUpExplanation(null)
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
        <h2 className="text-sm font-semibold text-[color:var(--text-primary)] mb-3">Lessons</h2>
        {!hasSyllabus ? (
          <p className="text-xs text-[color:var(--text-muted)]">
            Generate your syllabus first to see lessons.
          </p>
        ) : syllabusModules.length === 0 ? (
          <p className="text-xs text-[color:var(--text-muted)]">No lessons in syllabus.</p>
        ) : (
          <div className="space-y-4">
            {syllabusModules.map((mod) => (
              <div key={mod.module_id}>
                <p className="text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-muted)] mb-2">
                  {mod.title}
                </p>
                <ul className="space-y-1">
                  {(mod.lessons || []).map((lesson) => (
                    <li key={lesson.lesson_id}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedLesson(lesson)
                          setCurrentLesson(lesson)
                        }}
                        className={`w-full text-left rounded-lg px-3 py-2 text-xs transition-colors ${
                          displayLesson?.lesson_id === lesson.lesson_id
                            ? 'text-white'
                            : 'text-[color:var(--text-secondary)] hover:bg-white/10'
                        }`}
                        style={
                          displayLesson?.lesson_id === lesson.lesson_id
                            ? {
                                background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
                              }
                            : undefined
                        }
                      >
                        <span className="font-medium leading-snug">{lesson.title}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
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
            <h1 className="text-2xl font-bold text-[color:var(--text-primary)] mt-2 mb-4">
              {displayLesson.title}
            </h1>
            <div
              className="rounded-xl p-6"
              style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
            >
              {contentLoading ? (
                <p className="text-[color:var(--text-muted)]">Loading content…</p>
              ) : lesson ? (
                <>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] text-[color:var(--text-muted)]">
                      ~{lesson.duration_minutes} min read · Level: {level}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-700 text-slate-300">
                      Lesson
                    </span>
                  </div>
                  {lesson.sections?.map(renderSection)}

                  <div
                    className="mt-8 rounded-xl border p-5"
                    style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <ClipboardCheck className="h-5 w-5 text-sky-400" />
                      <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                        Quick Assessment (3 questions)
                      </h2>
                    </div>

                    {!assessmentOpen ? (
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
                              try {
                                const answers = assessmentQuestions.map((q) => ({
                                  question_id: q.id,
                                  answer_index: assessmentAnswers[q.id],
                                }))
                                const resp = await quickAssessmentApi.grade(displayLesson.lesson_id, resolvedTopic, answers as any)
                                mergeAnalyticsFromQA(resp.analytics)
                                setAssessmentResult(
                                  resp.grading
                                    ? { correct_count: resp.grading.correct_count, total: resp.grading.total }
                                    : null
                                )
                                setFollowUpExplanation(resp.follow_up_explanation ?? null)

                                if (resp.next_action === 'advance_to_next_lesson') {
                                  const idx = allLessons.findIndex((x) => x.lesson.lesson_id === displayLesson.lesson_id)
                                  const next = idx >= 0 ? allLessons[idx + 1] : null
                                  if (next) {
                                    setSelectedLesson(next.lesson)
                                    setCurrentLesson(next.lesson)
                                    setCurrentTopic((next.lesson as any).topic || next.lesson.lesson_id)
                                    setAssessmentOpen(false)
                                  }
                                }
                              } catch (err) {
                                // eslint-disable-next-line no-console
                                console.error(err)
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
    </div>
  )
}
