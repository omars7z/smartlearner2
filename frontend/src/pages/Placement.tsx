import { useState } from 'react'
import { motion } from 'framer-motion'
import Navbar from '../components/Navbar'

interface Question {
  id: string
  order: number
  total: number
  text: string
  difficulty: string
  topic: string
  options: string[]
}

interface PlacementResult {
  track: string
  score: number
  percentage: number
  level: string
  strong_topics: string[]
  weak_topics: string[]
  recommended_start_topic: string
}

const API_BASE = 'http://localhost:8000/api/v1'

export default function Placement() {
  const [track, setTrack] = useState<'python' | 'deep-learning'>('python')
  const [placementId, setPlacementId] = useState<number | null>(null)
  const [currentQuestion, setCurrentQuestion] = useState<Question | null>(null)
  const [result, setResult] = useState<PlacementResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedAnswer, setSelectedAnswer] = useState<number | null>(null)

  const startExam = async () => {
    setLoading(true)
    setError(null)
    setResult(null)
    setPlacementId(null)
    setCurrentQuestion(null)
    setSelectedAnswer(null)
    try {
      const token = localStorage.getItem('token')
      const res = await fetch(`${API_BASE}/placement/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ track }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setPlacementId(data.placement_id)
      setCurrentQuestion(data.questions[0]) // Assuming it returns all, but we'll show first
    } catch (err) {
      console.error(err)
      setError('Failed to start placement test. Check backend on localhost:8000.')
    } finally {
      setLoading(false)
    }
  }

  const submitAnswer = async () => {
    if (!placementId || !currentQuestion || selectedAnswer === null) return
    setLoading(true)
    setError(null)
    try {
      const token = localStorage.getItem('token')
      const res = await fetch(`${API_BASE}/placement/answer`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          placement_id: placementId,
          track,
          question_id: currentQuestion.id,
          answer_index: selectedAnswer,
        }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data.finished) {
        setResult(data.placement_result)
        setCurrentQuestion(null)
      } else {
        setCurrentQuestion(data.next_question)
        setSelectedAnswer(null)
      }
    } catch (err) {
      console.error(err)
      setError('Failed to submit answer.')
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
            Select a learning track, then answer questions one by one. The Placement Test Agent generates questions from the resource.
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

          {currentQuestion && (
            <div className="mt-4">
              <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    Question {currentQuestion.order} of {currentQuestion.total}: {currentQuestion.text}
                  </p>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {currentQuestion.difficulty}
                  </span>
                </div>
                <div className="space-y-1">
                  {currentQuestion.options.map((option, i) => (
                    <label
                      key={i}
                      className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"
                    >
                      <input
                        type="radio"
                        name="answer"
                        value={i}
                        checked={selectedAnswer === i}
                        onChange={() => setSelectedAnswer(i)}
                      />
                      <span>{option}</span>
                    </label>
                  ))}
                </div>
              </div>

              <button
                type="button"
                onClick={submitAnswer}
                disabled={loading || selectedAnswer === null}
                className="mt-4 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md hover:bg-emerald-700 disabled:opacity-60"
              >
                {loading ? 'Submitting...' : 'Submit Answer'}
              </button>
            </div>
          )}

          {result && (
            <div className="mt-8 rounded-xl border border-emerald-500/40 bg-emerald-50 dark:bg-emerald-900/20 p-4 text-sm text-emerald-900 dark:text-emerald-100">
              <p className="font-semibold mb-1">
                Placement result for track <span className="underline">{result.track}</span>:
              </p>
              <p className="mb-2">
                Level: <span className="font-bold uppercase">{result.level}</span> ({result.percentage}%)
              </p>
              <p>Correct answers: {result.score}</p>
              <p>Strong topics: {result.strong_topics.join(', ')}</p>
              <p>Weak topics: {result.weak_topics.join(', ')}</p>
              <p>Recommended start: {result.recommended_start_topic}</p>
            </div>
          )}
        </div>
      </main>
    </motion.div>
  )
}

