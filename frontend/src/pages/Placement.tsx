import { useState } from 'react'
import { motion } from 'framer-motion'
import Navbar from '../components/Navbar'

interface Question {
  id: string
  text: string
  level: 'easy' | 'medium' | 'hard'
  choices: string[]
}

interface PlacementExam {
  track: string
  questions: Question[]
}

interface PlacementResult {
  track: string
  level: 'beginner' | 'intermediate' | 'advanced'
  score_easy: number
  score_medium: number
  score_hard: number
}

const API_BASE = 'http://localhost:8000'

export default function Placement() {
  const [track, setTrack] = useState<'python' | 'deep-learning'>('python')
  const [exam, setExam] = useState<PlacementExam | null>(null)
  const [answers, setAnswers] = useState<Record<string, number>>({})
  const [result, setResult] = useState<PlacementResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const startExam = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(`${API_BASE}/api/placement/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ student_id: 'demo-student', track }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: PlacementExam = await res.json()
      setExam(data)
      setAnswers({})
    } catch (err) {
      console.error(err)
      setError('Failed to start placement test. Check backend on localhost:8000.')
    } finally {
      setLoading(false)
    }
  }

  const submitExam = async () => {
    if (!exam) return
    setLoading(true)
    setError(null)
    try {
      const payload = {
        student_id: 'demo-student',
        track: exam.track,
        answers: Object.entries(answers).map(([question_id, choice_index]) => ({
          question_id,
          choice_index,
        })),
      }
      const res = await fetch(`${API_BASE}/api/placement/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: PlacementResult = await res.json()
      setResult(data)
    } catch (err) {
      console.error(err)
      setError('Failed to submit placement test.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen bg-slate-50 dark:bg-slate-900"
    >
      <Navbar />
      <main className="max-w-6xl mx-auto px-4 py-12">
        <div className="glass-card rounded-2xl p-6 sm:p-10">
          <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-white mb-4">
            Placement Test (Dynamic per Track)
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
            Select a learning track, then let the Placement Test Agent generate an exam with easy,
            medium, and hard questions. The Exam Agent and Analytics Agent will infer your level
            (beginner / intermediate / advanced) based on your answers.
          </p>

          <div className="flex flex-wrap gap-4 items-center mb-6">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Track:
            </label>
            <select
              value={track}
              onChange={(e) => setTrack(e.target.value as 'python' | 'deep-learning')}
              className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2 text-sm text-slate-900 dark:text-slate-100"
            >
              <option value="python">Python Foundations</option>
              <option value="deep-learning">Deep Learning</option>
            </select>
            <button
              type="button"
              onClick={startExam}
              disabled={loading}
              className="rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] px-5 py-2.5 text-sm font-semibold text-white shadow-md hover:opacity-90 disabled:opacity-60"
            >
              {loading ? 'Preparing exam...' : 'Start Placement Test'}
            </button>
          </div>

          {error && <p className="text-sm text-rose-500 mb-4">{error}</p>}

          {exam && (
            <div className="mt-4 space-y-4">
              {exam.questions.map((q, idx) => (
                <div
                  key={q.id}
                  className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3"
                >
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                      Q{idx + 1}. {q.text}
                    </p>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                      {q.level}
                    </span>
                  </div>
                  <div className="space-y-1">
                    {q.choices.map((choice, i) => (
                      <label
                        key={i}
                        className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"
                      >
                        <input
                          type="radio"
                          name={q.id}
                          value={i}
                          checked={answers[q.id] === i}
                          onChange={() =>
                            setAnswers((prev) => ({
                              ...prev,
                              [q.id]: i,
                            }))
                          }
                        />
                        <span>{choice}</span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}

              <button
                type="button"
                onClick={submitExam}
                disabled={loading}
                className="mt-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-emerald-700 disabled:opacity-60"
              >
                {loading ? 'Submitting...' : 'Submit Answers'}
              </button>
            </div>
          )}

          {result && (
            <div className="mt-8 rounded-xl border border-emerald-500/40 bg-emerald-50 dark:bg-emerald-900/20 p-4 text-sm text-emerald-900 dark:text-emerald-100">
              <p className="font-semibold mb-1">
                Placement result for track <span className="underline">{result.track}</span>:
              </p>
              <p className="mb-2">
                Overall level:{' '}
                <span className="font-bold uppercase">{result.level}</span>
              </p>
              <p>
                Easy score: {(result.score_easy * 100).toFixed(0)}% — Medium score:{' '}
                {(result.score_medium * 100).toFixed(0)}% — Hard score:{' '}
                {(result.score_hard * 100).toFixed(0)}%
              </p>
            </div>
          )}
        </div>
      </main>
    </motion.div>
  )
}

