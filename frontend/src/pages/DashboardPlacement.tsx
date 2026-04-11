import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ClipboardList, ChevronDown } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useDashboard } from '../context/DashboardContext'
import { useToast } from '../context/ToastContext'
import { useAccentTheme } from '../hooks/useAccentTheme'
import { placementApi, type PlacementFullResult } from '../services/api'

type PlacementState = 'idle' | 'loading' | 'testing' | 'results'

interface NormalizedQuestion {
  question_id: string
  question_text: string
  options: { id: string; text: string }[]
  difficulty: string
  level_label?: string
  level_stage?: number
  levels_total?: number
}

function normalizeQuestion(data: Record<string, unknown> | null): NormalizedQuestion | null {
  if (!data) return null
  const rawOptions = (data.options as unknown) ?? []
  const optsArray: unknown[] = Array.isArray(rawOptions) ? rawOptions : []
  const hasOptObjects =
    optsArray.length > 0 &&
    typeof optsArray[0] === 'object' &&
    optsArray[0] != null &&
    'id' in (optsArray[0] as Record<string, unknown>) &&
    'text' in (optsArray[0] as Record<string, unknown>)
  return {
    question_id: (data.question_id as string) ?? (data.id as string) ?? '',
    question_text: (data.question_text as string) ?? (data.question as string) ?? (data.text as string) ?? '',
    level_label: (data.level_label as string) || undefined,
    level_stage: typeof data.level_stage === 'number' ? data.level_stage : undefined,
    levels_total: typeof data.levels_total === 'number' ? data.levels_total : undefined,
    options: hasOptObjects
      ? (optsArray as { id: string; text: string }[])
      : [
          { id: 'A', text: (data.option_a as string) ?? (data.A as string) ?? (optsArray[0] as string) ?? '' },
          { id: 'B', text: (data.option_b as string) ?? (data.B as string) ?? (optsArray[1] as string) ?? '' },
          { id: 'C', text: (data.option_c as string) ?? (data.C as string) ?? (optsArray[2] as string) ?? '' },
          { id: 'D', text: (data.option_d as string) ?? (data.D as string) ?? (optsArray[3] as string) ?? '' },
        ].filter((o) => o.text),
    difficulty: (data.difficulty as string) ?? 'medium',
  }
}

const TRACKS = [
  { id: 'python', label: 'Python Foundations' },
  { id: 'deep-learning', label: 'Deep Learning' },
  { id: 'nlp', label: 'NLP' },
] as const

function apiErrorDetail(err: unknown, fallback: string): string {
  const ax = err as { response?: { data?: { detail?: unknown } }; message?: string }
  const d = ax?.response?.data?.detail
  if (typeof d === 'string' && d.trim()) return d
  if (Array.isArray(d) && d.length) return d.map((x) => JSON.stringify(x)).join('; ')
  return ax?.message || fallback
}

export default function DashboardPlacement() {
  const { accentPrimary, accentSecondary } = useAccentTheme()
  const navigate = useNavigate()
  const { addToast } = useToast()
  const { setPlacementDone } = useDashboard()

  const [state, setState] = useState<PlacementState>('idle')
  const [busy, setBusy] = useState(false)
  const [currentQuestion, setCurrentQuestion] = useState<NormalizedQuestion | null>(null)
  const [questionNum, setQuestionNum] = useState(0)
  const QUESTIONS_PER_LEVEL = 5
  const [totalQuestions, setTotalQuestions] = useState(QUESTIONS_PER_LEVEL)
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null)
  const [results, setResults] = useState<PlacementFullResult | null>(null)
  const [trackId, setTrackId] = useState<string>('python')
  const [placementId, setPlacementId] = useState<number | null>(null)

  const startTest = async () => {
    setState('loading')
    setBusy(true)
    try {
      const res = await placementApi.start(trackId)
      if (typeof res.placement_id === 'number') {
        setPlacementId(res.placement_id)
      } else {
        setPlacementId(null)
      }
      const rawAny = (res as any)?.next_question ?? (res as any)?.question ?? res
      const q = normalizeQuestion(rawAny as Record<string, unknown>)
      if (!q || !q.question_text) {
        addToast('error', 'Failed to start test: no question returned')
        setState('idle')
        return
      }
      const total = (rawAny as any)?.total ?? 10
      setCurrentQuestion(q)
      setQuestionNum(1)
      setTotalQuestions(total)
      setSelectedAnswer(null)
      setState('testing')
    } catch (err) {
      addToast('error', apiErrorDetail(err, 'Failed to start test'))
      setState('idle')
    } finally {
      setBusy(false)
    }
  }

  const submitAnswer = async () => {
    if (!currentQuestion || selectedAnswer == null || placementId == null) return
    setState('loading')
    setBusy(true)
    try {
      const answerIndex = currentQuestion.options.findIndex((o) => o.id === selectedAnswer)
      const res = await placementApi.answer(
        placementId,
        trackId,
        currentQuestion.question_id,
        answerIndex >= 0 ? answerIndex : 0
      )
      const data = res as {
        finished?: boolean
        completed?: boolean
        placement_result?: PlacementFullResult
        next_question?: Record<string, unknown>
        question?: Record<string, unknown>
      }
      const finished = data.finished ?? data.completed ?? false
      const nextRaw = (data as any).next_question ?? (data as any).question ?? res

      if (finished) {
        const placementResult = data.placement_result ?? (res as { placement_result?: PlacementFullResult }).placement_result ?? null
        if (placementResult) {
          setPlacementDone(
            { level: placementResult.level, score: placementResult.score, track: placementResult.track, percentage: placementResult.percentage },
            placementResult,
            placementId
          )
          try {
            localStorage.setItem('placement_result', JSON.stringify(placementResult))
            localStorage.setItem('current_track', placementResult.track ?? trackId)
          } catch (_) {}
        }
        setResults(placementResult ?? {
          track: trackId,
          score: 0,
          percentage: 0,
          level: 'beginner',
          strong_topics: [],
          weak_topics: [],
          recommended_start_topic: '',
        })
        setCurrentQuestion(null)
        setSelectedAnswer(null)
        setState('results')
        addToast('success', 'Placement test completed! 🎉')
      } else {
        const q = normalizeQuestion(nextRaw as Record<string, unknown>)
        setCurrentQuestion(q)
        setQuestionNum((prev) => prev + 1)
        setSelectedAnswer(null)
        setState('testing')
      }
    } catch (err) {
      addToast('error', apiErrorDetail(err, 'Failed to submit answer'))
      setState('testing')
    } finally {
      setBusy(false)
    }
  }

  const handleGenerateSyllabus = () => {
    navigate('/dashboard/syllabus', { state: { autoGenerate: true } })
  }

  return (
    <div
      className="flex-1 min-w-0 overflow-y-auto p-6"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="max-w-2xl mx-auto">
        <AnimatePresence mode="wait">
          {state === 'idle' && (
            <motion.div
              key="idle"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-2xl p-6 sm:p-8"
              style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
            >
              <div className="flex items-center gap-3 mb-6">
                <div
                  className="h-12 w-12 rounded-2xl flex items-center justify-center"
                  style={{ background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` }}
                >
                  <ClipboardList className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-[color:var(--text-primary)]">Placement Test</h1>
                  <p className="text-sm text-[color:var(--text-secondary)]">Choose a track and start to get your level</p>
                </div>
              </div>
              <label className="block text-sm font-medium text-[color:var(--text-secondary)] mb-2">Track</label>
              <div className="flex flex-wrap gap-2 mb-6">
                {TRACKS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setTrackId(t.id)}
                    className="rounded-xl px-4 py-2.5 text-sm font-medium transition-all"
                    style={{
                      backgroundColor: trackId === t.id ? accentPrimary : 'var(--bg-input)',
                      color: trackId === t.id ? 'white' : 'var(--text-primary)',
                      border: `1px solid ${trackId === t.id ? 'transparent' : 'var(--border-color)'}`,
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={startTest}
                disabled={busy}
                className="w-full rounded-xl py-4 text-lg font-semibold text-white disabled:opacity-60 transition shadow-lg hover:opacity-90"
                style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
              >
                {busy ? 'Starting…' : 'Start Placement Test'}
              </button>
            </motion.div>
          )}

          {state === 'loading' && !currentQuestion && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="rounded-2xl p-12 text-center"
              style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
            >
              <div className="animate-spin h-10 w-10 border-2 border-t-transparent rounded-full mx-auto mb-4" style={{ borderColor: accentPrimary }} />
              <p className="text-[color:var(--text-primary)]">Preparing your placement test…</p>
            </motion.div>
          )}

          {state === 'testing' && currentQuestion && (
            <motion.div
              key="testing"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-2xl p-6 sm:p-8"
              style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
            >
              <div className="flex gap-2 mb-4 flex-wrap">
                <span className="rounded-full bg-sky-500/20 text-sky-300 px-2.5 py-0.5 text-xs font-medium border border-sky-400/40">Placement Agent</span>
                <span className="text-slate-500">→</span>
                <span className="rounded-full bg-violet-500/20 text-violet-300 px-2.5 py-0.5 text-xs font-medium border border-violet-400/40">Exam Agent</span>
                <span className="text-slate-500">→</span>
                <span className="rounded-full bg-emerald-500/20 text-emerald-300 px-2.5 py-0.5 text-xs font-medium border border-emerald-400/40">Analytics Agent</span>
              </div>
              <div className="h-2 rounded-full bg-slate-700 overflow-hidden mb-6">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${(questionNum / Math.max(totalQuestions, 1)) * 100}%`,
                    background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})`,
                  }}
                />
              </div>
              {(currentQuestion.level_stage != null || currentQuestion.level_label) && (
                <p className="text-xs text-[color:var(--text-secondary)] mb-1">
                  {currentQuestion.level_stage != null && currentQuestion.levels_total != null
                    ? `Stage ${currentQuestion.level_stage} of ${currentQuestion.levels_total}`
                    : null}
                  {currentQuestion.level_label
                    ? `${currentQuestion.level_stage != null ? ' · ' : ''}${currentQuestion.level_label}`
                    : null}
                </p>
              )}
              <p className="text-sm text-[color:var(--text-muted)] mb-2">
                Question {questionNum} of {totalQuestions} (need 4/5 to advance)
              </p>
              <h2 className="text-xl font-semibold text-[color:var(--text-primary)] mb-6 leading-snug">
                {currentQuestion.question_text}
              </h2>
              <div className="space-y-3 mb-8">
                {currentQuestion.options.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setSelectedAnswer(opt.id)}
                    className="w-full text-left rounded-xl p-4 transition-all border-2 hover:shadow-md"
                    style={{
                      backgroundColor: selectedAnswer === opt.id ? `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` : 'var(--bg-input)',
                      borderColor: selectedAnswer === opt.id ? 'transparent' : 'var(--border-color)',
                      background: selectedAnswer === opt.id ? `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` : undefined,
                      color: selectedAnswer === opt.id ? 'white' : 'var(--text-primary)',
                    }}
                  >
                    <span className="font-medium mr-2">{opt.id}.</span>
                    <span>{opt.text}</span>
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={submitAnswer}
                disabled={selectedAnswer == null || busy}
                className="w-full rounded-xl py-3 font-semibold text-white disabled:opacity-50 transition"
                style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
              >
                {busy ? 'Submitting…' : 'Submit answer'}
              </button>
            </motion.div>
          )}

          {state === 'results' && results && (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="rounded-2xl p-6 sm:p-8"
              style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
            >
              <h2 className="text-2xl font-bold text-[color:var(--text-primary)] mb-6 text-center">Your Result</h2>
              <div className="flex justify-center mb-6">
                <div
                  className="px-6 py-2 rounded-xl text-lg font-bold uppercase"
                  style={{
                    color: 'white',
                    backgroundColor:
                      results.level === 'very_advanced'
                        ? '#7c3aed'
                        : results.level === 'advanced'
                          ? '#dc2626'
                          : results.level === 'intermediate'
                            ? '#ca8a04'
                            : '#16a34a',
                  }}
                >
                  {results.level.replace(/_/g, ' ')}
                </div>
              </div>
              <p className="text-center text-[color:var(--text-muted)] text-sm mb-2">
                {results.stopped_reason === 'completed_all'
                  ? 'You passed all four stages.'
                  : results.stopped_reason === 'failed_level'
                    ? 'Stopped at this stage (fewer than 4 correct in the last block).'
                    : null}
              </p>
              {results.levels_passed && results.levels_passed.length > 0 && (
                <p className="text-center text-[color:var(--text-secondary)] text-xs mb-4">
                  Stages cleared: {results.levels_passed.map((l) => l.replace(/_/g, ' ')).join(' → ')}
                </p>
              )}
              <p className="text-center text-[color:var(--text-primary)] mb-6">
                Last stage:{' '}
                <strong>
                  {results.last_block_correct ?? '—'}/{results.last_block_total ?? 5}
                </strong>{' '}
                correct (need 4/5 to advance).
                {results.total_answered != null && (
                  <span className="block text-sm text-[color:var(--text-muted)] mt-1">
                    Overall: {results.score}/{results.total_answered} correct (
                    {results.percentage}%)
                  </span>
                )}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                <div className="rounded-xl p-4 border border-emerald-500/30 bg-emerald-500/10">
                  <p className="text-sm font-medium text-emerald-300 mb-2">Strong topics</p>
                  <ul className="space-y-1">
                    {(results.strong_topics?.length ? results.strong_topics : ['—']).map((t, i) => (
                      <li key={i} className="text-sm text-emerald-200 flex items-center gap-2">
                        <span>✓</span> {t}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-xl p-4 border border-rose-500/30 bg-rose-500/10">
                  <p className="text-sm font-medium text-rose-300 mb-2">Weak topics</p>
                  <ul className="space-y-1">
                    {(results.weak_topics?.length ? results.weak_topics : ['—']).map((t, i) => (
                      <li key={i} className="text-sm text-rose-200 flex items-center gap-2">
                        <span>✗</span> {t}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              <button
                type="button"
                onClick={handleGenerateSyllabus}
                className="w-full rounded-xl py-4 font-semibold text-white flex items-center justify-center gap-2"
                style={{ background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})` }}
              >
                Generate My Syllabus <ChevronDown className="h-5 w-5 rotate-[-90deg]" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
