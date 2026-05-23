import { useState, useEffect, useMemo, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { useDashboard } from '../context/DashboardContext'
import { useToast } from '../context/ToastContext'
import { useAccentTheme } from '../hooks/useAccentTheme'
import { examsApi, lessonsApi, type ExamQuestionDto } from '../services/api'
import {
  buildCompletedExamLessonOptions,
  COMPREHENSIVE_EXAM_LESSON_ID,
  isTrackReadyForComprehensiveExam,
} from '../utils/examEligible'
import { extractCourseIdFromModules } from '../utils/lessonProgressUi'
import type { LessonProgressEntry } from '../utils/lessonProgressUi'

type ExamState = 'setup' | 'generating' | 'taking' | 'results'

interface PerQuestionResult {
  question_id: string
  question_text: string
  correct: boolean
  student_answer: string
  correct_answer: string
  explanation?: string
}

interface ExamResults {
  score: number
  total: number
  percentage: number
  passed: boolean
  results: PerQuestionResult[]
  feedback: string
}

const LETTERS = ['A', 'B', 'C', 'D']

function normalizeQuestions(raw: unknown): ExamQuestionDto[] {
  const data = raw as {
    exam?: { questions?: ExamQuestionDto[] }
    questions?: ExamQuestionDto[]
    result?: { questions?: ExamQuestionDto[] }
  }
  const list = data?.result?.questions ?? data?.exam?.questions ?? data?.questions ?? []
  return Array.isArray(list) ? list : []
}

function calculateLocally(
  questions: ExamQuestionDto[],
  answers: Record<string, string>
): ExamResults {
  let score = 0
  const perQ: PerQuestionResult[] = questions.map((q) => {
    const qid = q.question_id ?? q.id
    const studentLetter = answers[qid]
    const correctLetter = q.correct_answer ?? LETTERS[q.correct_index ?? 0]
    const correct = studentLetter === correctLetter
    if (correct) score++
    return {
      question_id: qid,
      question_text: q.question_text ?? q.text,
      correct,
      student_answer: studentLetter ?? '—',
      correct_answer: correctLetter,
      explanation: q.explanation ?? '',
    }
  })
  const total = questions.length
  const pct = total ? Math.round((score / total) * 100) : 0
  const feedback =
    pct >= 90 ? '🎉 Excellent!' : pct >= 70 ? '👍 Good job!' : pct >= 50 ? '📚 Keep practicing!' : '💪 Review the material'
  return {
    score,
    total,
    percentage: pct,
    passed: pct >= 60,
    results: perQ,
    feedback,
  }
}

export default function DashboardExams() {
  const { accentPrimary, accentSecondary } = useAccentTheme()
  const {
    placementDone,
    placementResult,
    syllabusModules,
    setFirstExamTaken,
    mergeAnalyticsFromQA,
  } = useDashboard()
  const { addToast } = useToast()
  const navigate = useNavigate()

  const [examState, setExamState] = useState<ExamState>('setup')
  const [numQ, setNumQ] = useState(5)
  const [selectedTarget, setSelectedTarget] = useState('')
  const [questions, setQuestions] = useState<ExamQuestionDto[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [results, setResults] = useState<ExamResults | null>(null)
  const [progressMap, setProgressMap] = useState<Record<string, LessonProgressEntry>>({})
  const [progressLoading, setProgressLoading] = useState(false)
  const [assessableProgress, setAssessableProgress] = useState({ completed: 0, total: 0 })

  const courseId = useMemo(() => extractCourseIdFromModules(syllabusModules), [syllabusModules])

  const placementLevel = useMemo(() => {
    const raw = (placementResult?.level || 'beginner').replace(/-/g, '_').toLowerCase()
    if (raw === 'very_advanced' || raw === 'veryadvanced') return 'very_advanced' as const
    if (raw === 'intermediate' || raw === 'advanced' || raw === 'beginner') return raw
    return 'beginner' as const
  }, [placementResult?.level])

  const completedLessonOptions = useMemo(
    () => buildCompletedExamLessonOptions(syllabusModules, progressMap),
    [syllabusModules, progressMap],
  )

  const trackComprehensiveReady = useMemo(
    () => isTrackReadyForComprehensiveExam(assessableProgress.completed, assessableProgress.total),
    [assessableProgress],
  )

  const examSelectOptions = useMemo(() => {
    const opts = completedLessonOptions.map((o) => ({
      value: o.lesson_id,
      label: `${o.label} — ${o.moduleTitle}`,
    }))
    if (trackComprehensiveReady) {
      opts.push({
        value: COMPREHENSIVE_EXAM_LESSON_ID,
        label: '🎓 Comprehensive track exam (all completed topics)',
      })
    }
    return opts
  }, [completedLessonOptions, trackComprehensiveReady])

  const refreshProgress = useCallback(async () => {
    if (!courseId) return
    setProgressLoading(true)
    try {
      const data = await lessonsApi.getProgress(courseId)
      setProgressMap(data.lessons ?? {})
      setAssessableProgress({
        completed: data.completed_assessable ?? 0,
        total: data.total_assessable ?? 0,
      })
    } catch {
      setProgressMap({})
      setAssessableProgress({ completed: 0, total: 0 })
    } finally {
      setProgressLoading(false)
    }
  }, [courseId])

  useEffect(() => {
    void refreshProgress()
  }, [refreshProgress, syllabusModules])

  useEffect(() => {
    if (!examSelectOptions.length) {
      setSelectedTarget('')
      return
    }
    setSelectedTarget((prev) =>
      prev && examSelectOptions.some((o) => o.value === prev) ? prev : examSelectOptions[0].value,
    )
  }, [examSelectOptions])

  const isComprehensiveSelected = selectedTarget === COMPREHENSIVE_EXAM_LESSON_ID
  const canGenerate = Boolean(selectedTarget) && examSelectOptions.length > 0

  const generateExam = async () => {
    if (!selectedTarget || !courseId) return
    setExamState('generating')
    try {
      const res = await examsApi.generate(selectedTarget, {
        level: placementLevel,
        question_count: numQ,
        course_id: courseId,
      })
      const qs = normalizeQuestions(res)
      if (qs.length === 0) {
        addToast('error', 'No questions generated, try again')
        setExamState('setup')
        return
      }
      setQuestions(qs)
      setAnswers({})
      setResults(null)
      setExamState('taking')
      addToast('success', 'Exam ready!')
    } catch (err) {
      addToast('error', 'Failed to generate exam')
      setExamState('setup')
    }
  }

  const submitExam = async () => {
    if (!selectedTarget || !courseId) return
    try {
      const answerList = questions.map((q) => {
        const qid = q.question_id ?? q.id
        const letter = answers[qid]
        const idx = letter ? LETTERS.indexOf(letter) : 0
        return { question_id: qid, answer_index: idx >= 0 ? idx : 0 }
      })
      const gradeRes = await examsApi.grade(selectedTarget, answerList, { course_id: courseId })
      const backendResults = gradeRes?.result
      let finalPct = 0
      if (backendResults?.results?.length) {
        const total = backendResults.total ?? backendResults.results.length
        const score = backendResults.score ?? backendResults.results.filter((r) => r.correct).length
        finalPct = backendResults.overall_score ?? (total ? Math.round((score / total) * 100) : 0)
        setResults({
          score,
          total,
          percentage: finalPct,
          passed: finalPct >= 60,
          results: backendResults.results,
          feedback: finalPct >= 90 ? '🎉 Excellent!' : finalPct >= 70 ? '👍 Good job!' : finalPct >= 50 ? '📚 Keep practicing!' : '💪 Review the material',
        })
      } else {
        const localResults = calculateLocally(questions, answers)
        finalPct = localResults.percentage
        setResults(localResults)
      }
      if (backendResults?.analytics) {
        mergeAnalyticsFromQA(backendResults.analytics)
      }
      setFirstExamTaken(true)
      setExamState('results')
      void refreshProgress()
      addToast('success', `Score: ${finalPct}%`)
    } catch (err) {
      const localResults = calculateLocally(questions, answers)
      setResults(localResults)
      setFirstExamTaken(true)
      setExamState('results')
      void refreshProgress()
      addToast('success', `Score: ${localResults.percentage}% (saved locally)`)
    }
  }

  const answerCount = Object.keys(answers).length
  const allAnswered = questions.length > 0 && answerCount >= questions.length

  if (!placementDone) {
    return (
      <div
        className="flex-1 min-w-0 overflow-y-auto p-6 flex items-center justify-center"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <div
          className="rounded-2xl border-2 border-dashed p-12 text-center max-w-md"
          style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
        >
          <Lock className="h-14 w-14 mx-auto text-slate-500 mb-4" />
          <h2 className="text-xl font-semibold text-[color:var(--text-primary)] mb-2">Exams locked</h2>
          <p className="text-sm text-[color:var(--text-secondary)] mb-6">
            Complete the placement test first to unlock exams.
          </p>
          <button
            type="button"
            onClick={() => navigate('/dashboard/placement')}
            className="rounded-xl py-3 px-6 text-white font-semibold"
            style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
          >
            Take Placement Test →
          </button>
        </div>
      </div>
    )
  }

  return (
    <div
      className="flex-1 min-w-0 overflow-y-auto p-6"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold text-[color:var(--text-primary)] mb-6">Exams</h1>

        <AnimatePresence mode="wait">
          {examState === 'setup' && (
            <motion.div
              key="setup"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-2xl p-6 border setup-card"
              style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
            >
              <h2 className="text-lg font-semibold text-[color:var(--text-primary)] mb-2">Generate Adaptive Exam</h2>
              <p className="text-xs text-[color:var(--text-secondary)] mb-4">
                Only lessons you completed (quiz passed) appear here.
                {assessableProgress.total > 0 && (
                  <>
                    {' '}
                    Track progress: {assessableProgress.completed}/{assessableProgress.total} topics.
                  </>
                )}
              </p>
              <label className="block text-sm font-medium text-[color:var(--text-secondary)] mb-1">
                Completed lesson or track exam
              </label>
              {progressLoading ? (
                <p className="text-sm text-[color:var(--text-secondary)] mb-4">Loading your progress…</p>
              ) : examSelectOptions.length > 0 ? (
                <select
                  value={selectedTarget}
                  onChange={(e) => setSelectedTarget(e.target.value)}
                  className="w-full rounded-xl px-3 py-2.5 text-sm mb-4 focus:outline-none focus:ring-2"
                  style={{ backgroundColor: 'var(--bg-input)', color: 'var(--text-primary)' }}
                >
                  {examSelectOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-sm text-amber-300/90 mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2">
                  Complete at least one lesson quiz in Lessons to unlock per-lesson exams.
                </p>
              )}
              <p className="text-xs text-[color:var(--text-secondary)] mb-4">
                Placement level: <span className="font-medium text-[color:var(--text-primary)]">{placementLevel.replace(/_/g, ' ')}</span>
                {isComprehensiveSelected && ' · questions span the full track'}
              </p>
              <label className="block text-sm font-medium text-[color:var(--text-secondary)] mb-1">Number of questions</label>
              <select
                value={numQ}
                onChange={(e) => setNumQ(Number(e.target.value))}
                className="w-full rounded-xl px-3 py-2.5 text-sm mb-6 focus:outline-none focus:ring-2"
                style={{ backgroundColor: 'var(--bg-input)', color: 'var(--text-primary)' }}
              >
                <option value={3}>3 questions (Quick)</option>
                <option value={5}>5 questions (Standard)</option>
                <option value={10}>10 questions (Full)</option>
              </select>
              <button
                type="button"
                onClick={generateExam}
                disabled={!canGenerate || progressLoading}
                className="w-full rounded-xl py-3 font-semibold text-white gradient-btn disabled:opacity-50"
                style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
              >
                {isComprehensiveSelected ? 'Generate comprehensive exam' : 'Generate lesson exam'}
              </button>
            </motion.div>
          )}

          {examState === 'generating' && (
            <motion.div
              key="generating"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="rounded-2xl border p-12 text-center py-16"
              style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
            >
              <div
                className="animate-spin h-12 w-12 border-2 border-t-transparent rounded-full mx-auto mb-4"
                style={{ borderColor: accentPrimary }}
              />
              <p className="text-[color:var(--text-primary)] font-medium">Exam Agent is creating questions…</p>
            </motion.div>
          )}

          {examState === 'taking' && questions.length > 0 && (
            <motion.div
              key="taking"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-6"
            >
              {questions.map((q, idx) => {
                const qid = q.question_id ?? q.id
                const qText = q.question_text ?? q.text
                const opts = q.options ?? []
                return (
                  <div
                    key={qid}
                    className="rounded-xl p-4 border question-card"
                    style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
                  >
                    <div className="flex items-center gap-2 mb-2 q-header">
                      <span className="text-sm font-semibold text-[color:var(--text-primary)]">Q{idx + 1}</span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded ${q.difficulty === 'hard' ? 'bg-rose-500/20 text-rose-300' : q.difficulty === 'medium' ? 'bg-amber-500/20 text-amber-300' : 'bg-emerald-500/20 text-emerald-300'}`}
                      >
                        {q.difficulty}
                      </span>
                    </div>
                    <p className="q-text text-[color:var(--text-primary)] mb-4">{qText}</p>
                    <div className="options-grid space-y-2">
                      {opts.map((opt, i) => {
                        const letter = LETTERS[i] ?? String(i)
                        const isSelected = answers[qid] === letter
                        return (
                          <button
                            key={i}
                            type="button"
                            onClick={() => setAnswers((prev) => ({ ...prev, [qid]: letter }))}
                            className={`w-full text-left rounded-xl p-3 flex items-center gap-3 transition border-2 ${
                              isSelected ? 'selected' : 'normal'
                            }`}
                            style={{
                              backgroundColor: isSelected ? `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` : 'var(--bg-input)',
                              background: isSelected ? `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` : undefined,
                              color: isSelected ? 'white' : 'var(--text-primary)',
                              borderColor: isSelected ? 'transparent' : 'var(--border-color)',
                            }}
                          >
                            <span className="opt-letter font-semibold w-6">{letter}.</span>
                            <span>{typeof opt === 'string' ? opt : (opt as { text?: string }).text ?? ''}</span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
              <button
                type="button"
                onClick={submitExam}
                disabled={!allAnswered}
                className="w-full rounded-xl py-3 font-semibold text-white submit-btn disabled:opacity-50"
                style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
              >
                Submit Exam ({answerCount}/{questions.length} answered)
              </button>
            </motion.div>
          )}

          {examState === 'results' && results && (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="rounded-2xl border p-6 results-card"
              style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
            >
              <div className="text-center mb-6">
                <div
                  className="score-circle w-24 h-24 rounded-full mx-auto flex flex-col items-center justify-center text-white mb-3"
                  style={{ background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` }}
                >
                  <span className="score-num text-lg font-bold">{results.score}/{results.total}</span>
                  <span className="score-pct text-2xl font-bold">{results.percentage}%</span>
                </div>
                <span
                  className={`inline-block px-4 py-1.5 rounded-full text-sm font-semibold ${
                    results.passed ? 'pass-badge bg-emerald-500/20 text-emerald-300' : 'fail-badge bg-rose-500/20 text-rose-300'
                  }`}
                >
                  {results.passed ? '✅ Passed' : '❌ Not passed'}
                </span>
                <p className="feedback mt-3 text-[color:var(--text-primary)]">{results.feedback}</p>
              </div>
              <div className="space-y-4 mb-6">
                {results.results?.map((r, i) => (
                  <div
                    key={i}
                    className={`rounded-xl p-3 border ${r.correct ? 'correct-q border-emerald-500/30 bg-emerald-500/5' : 'wrong-q border-rose-500/30 bg-rose-500/5'}`}
                  >
                    <p className="text-sm font-medium text-[color:var(--text-primary)]">
                      {r.correct ? '✅' : '❌'} Q{i + 1}: {r.question_text}
                    </p>
                    <p className="text-xs text-[color:var(--text-secondary)] mt-1">
                      Your answer: {r.student_answer} | Correct: {r.correct_answer}
                    </p>
                    {r.explanation && (
                      <p className="explanation text-xs text-slate-400 mt-2">💡 {r.explanation}</p>
                    )}
                  </div>
                ))}
              </div>
              <div className="result-actions flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={() => { setQuestions([]); setResults(null); setAnswers({}); void generateExam() }}
                  className="rounded-xl py-2.5 px-4 text-sm font-semibold border"
                  style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
                >
                  Try Again
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/dashboard')}
                  className="rounded-xl py-2.5 px-4 text-sm font-semibold text-white"
                  style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
                >
                  Back to Dashboard
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/dashboard/qa')}
                  className="rounded-xl py-2.5 px-4 text-sm font-semibold border"
                  style={{ borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
                >
                  Ask About Mistakes
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
