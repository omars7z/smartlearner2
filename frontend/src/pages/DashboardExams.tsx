import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Lock } from 'lucide-react'
import { useDashboard } from '../context/DashboardContext'
import { useToast } from '../context/ToastContext'
import { useAccentTheme } from '../hooks/useAccentTheme'
import { examsApi } from '../services/api'
import type { ExamQuestionDto } from '../services/api'

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
  const data = raw as { exam?: { questions?: ExamQuestionDto[] }; questions?: ExamQuestionDto[] }
  const list = data?.exam?.questions ?? data?.questions ?? []
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
  const { placementDone, syllabusModules, setFirstExamTaken } = useDashboard()
  const { addToast } = useToast()
  const navigate = useNavigate()

  const [examState, setExamState] = useState<ExamState>('setup')
  const [topic, setTopic] = useState('Python Lists')
  const [level, setLevel] = useState<'beginner' | 'intermediate' | 'advanced'>('beginner')
  const [numQ, setNumQ] = useState(5)
  const [lessonId, setLessonId] = useState('py-1-1')
  const [questions, setQuestions] = useState<ExamQuestionDto[]>([])
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [results, setResults] = useState<ExamResults | null>(null)
  const [currentLessonId, setCurrentLessonId] = useState('py-1-1')

  const lessonsFromSyllabus = syllabusModules.flatMap((m) => m.lessons ?? [])

  useEffect(() => {
    if (lessonsFromSyllabus.length) {
      setLessonId(lessonsFromSyllabus[0].lesson_id)
      setCurrentLessonId(lessonsFromSyllabus[0].lesson_id)
    }
  }, [lessonsFromSyllabus.length])

  const generateExam = async () => {
    setExamState('generating')
    const lid = lessonsFromSyllabus.length ? lessonId : currentLessonId
    try {
      const res = await examsApi.generate(lid)
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
    const lid = lessonsFromSyllabus.length ? lessonId : currentLessonId
    try {
      const answerList = questions.map((q) => {
        const qid = q.question_id ?? q.id
        const letter = answers[qid]
        const idx = letter ? LETTERS.indexOf(letter) : 0
        return { question_id: qid, answer_index: idx >= 0 ? idx : 0 }
      })
      await examsApi.grade(lid, answerList)
      const localResults = calculateLocally(questions, answers)
      setResults(localResults)
      setFirstExamTaken(true)
      setExamState('results')
      addToast('success', `Score: ${localResults.percentage}%`)
    } catch (err) {
      const localResults = calculateLocally(questions, answers)
      setResults(localResults)
      setFirstExamTaken(true)
      setExamState('results')
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
              <h2 className="text-lg font-semibold text-[color:var(--text-primary)] mb-4">Generate Adaptive Exam</h2>
              <label className="block text-sm font-medium text-[color:var(--text-secondary)] mb-1">Topic / Lesson</label>
              {lessonsFromSyllabus.length > 0 ? (
                <select
                  value={lessonId}
                  onChange={(e) => setLessonId(e.target.value)}
                  className="w-full rounded-xl px-3 py-2.5 text-sm mb-4 focus:outline-none focus:ring-2"
                  style={{ backgroundColor: 'var(--bg-input)', color: 'var(--text-primary)' }}
                >
                  {lessonsFromSyllabus.map((l) => (
                    <option key={l.lesson_id} value={l.lesson_id}>
                      {l.title} ({l.topic})
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="e.g. Python Lists, Neural Networks..."
                  className="w-full rounded-xl px-3 py-2.5 text-sm mb-4 focus:outline-none focus:ring-2"
                  style={{ backgroundColor: 'var(--bg-input)', color: 'var(--text-primary)' }}
                />
              )}
              <label className="block text-sm font-medium text-[color:var(--text-secondary)] mb-2">Level</label>
              <div className="flex gap-2 mb-4 level-pills">
                {(['beginner', 'intermediate', 'advanced'] as const).map((l) => (
                  <button
                    key={l}
                    type="button"
                    onClick={() => setLevel(l)}
                    className={`rounded-xl px-4 py-2 text-sm font-medium transition ${
                      level === l ? 'active text-white' : ''
                    }`}
                    style={{
                      backgroundColor: level === l ? accentPrimary : 'var(--bg-input)',
                      color: level === l ? 'white' : 'var(--text-primary)',
                      border: `1px solid ${level === l ? 'transparent' : 'var(--border-color)'}`,
                    }}
                  >
                    {l}
                  </button>
                ))}
              </div>
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
                className="w-full rounded-xl py-3 font-semibold text-white gradient-btn"
                style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
              >
                Generate Exam
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
                  onClick={() => { setExamState('setup'); setQuestions([]); setResults(null) }}
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
