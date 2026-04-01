import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  ClipboardList,
  BookOpen,
  Award,
  TrendingUp,
  ArrowRight,
  ChevronDown,
  Brain,
  Zap,
  Map,
  CheckCircle,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAccentTheme } from '../hooks/useAccentTheme'
import { useDashboard } from '../context/DashboardContext'
import { useToast } from '../context/ToastContext'
import {
  placementApi,
  type PlacementQuestionDto,
  type PlacementFullResult,
  syllabusApi,
} from '../services/api'

export default function DashboardHome() {
  const { accentPrimary, accentSecondary } = useAccentTheme()
  const navigate = useNavigate()
  const { addToast } = useToast()
  const {
    placementDone,
    placementResult,
    fullPlacementResult,
    setPlacementDone,
    syllabusModules,
    setSyllabusModules,
    syllabusGenerated,
    firstExamTaken,
    overallMastery,
  } = useDashboard()

  const [track, setTrack] = useState<string>('python')
  const [placementId, setPlacementId] = useState<number | null>(null)
  const [currentQuestion, setCurrentQuestion] = useState<PlacementQuestionDto | null>(null)
  const [selectedOption, setSelectedOption] = useState<number | null>(null)
  const [placementError, setPlacementError] = useState<string | null>(null)
  const [placementLoading, setPlacementLoading] = useState(false)

  const [syllabusLoading, setSyllabusLoading] = useState(false)

  const startPlacement = async () => {
    setPlacementLoading(true)
    setPlacementError(null)
    try {
      const data = await placementApi.start(track)
      setPlacementId(typeof data.placement_id === 'number' ? data.placement_id : null)
      if (!data.next_question) {
        setPlacementError('Placement agent did not return a question.')
      } else {
        setCurrentQuestion(data.next_question)
        setSelectedOption(null)
      }
    } catch (err) {
      console.error(err)
      setPlacementError('Could not start placement test.')
      addToast('error', 'Could not start placement test.')
    } finally {
      setPlacementLoading(false)
    }
  }

  const submitPlacement = async () => {
    if (!currentQuestion || selectedOption === null || placementId === null) return
    setPlacementLoading(true)
    setPlacementError(null)
    try {
      const data = await placementApi.answer(placementId, track, currentQuestion.id, selectedOption)
      if (data.finished && data.placement_result) {
        const full = data.placement_result as PlacementFullResult
        setPlacementDone(
          {
            level: full.level,
            score: full.score,
            track: full.track,
            percentage: full.percentage,
          },
          full,
          placementId
        )
        setCurrentQuestion(null)
        setSelectedOption(null)
        addToast('success', 'Placement test completed! 🎉')
      } else if (data.next_question) {
        setCurrentQuestion(data.next_question)
        setSelectedOption(null)
      }
    } catch (err) {
      console.error(err)
      setPlacementError('Failed to submit placement test.')
      addToast('error', 'Failed to submit placement test.')
    } finally {
      setPlacementLoading(false)
    }
  }

  const handleGenerateSyllabus = async () => {
    if (!fullPlacementResult || !placementId) {
      addToast('error', 'Complete the placement test first.')
      return
    }
    setSyllabusLoading(true)
    try {
      const data = await syllabusApi.generate(placementId, `Python ${fullPlacementResult.level} Course`)
      const modules = data.result?.syllabus ?? []
      if (modules.length) {
        setSyllabusModules(modules)
        addToast('success', 'Syllabus generated! 🎉')
        navigate('/dashboard/syllabus')
      } else {
        addToast('error', 'Syllabus generator returned an empty plan.')
      }
    } catch (err) {
      console.error(err)
      addToast('error', 'Failed to generate syllabus.')
    } finally {
      setSyllabusLoading(false)
    }
  }

  const handlePreviewExam = () => {
    if (!placementDone) {
      addToast('info', 'Complete placement test first to unlock exams.')
      navigate('/dashboard/placement')
      return
    }
    navigate('/dashboard/exams')
  }

  return (
    <>
      <div
        className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden p-6"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <div className="max-w-6xl mx-auto space-y-5">
          {/* HERO Placement Card - full width */}
          <motion.section
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            className="rounded-2xl min-h-[200px] flex flex-col lg:flex-row overflow-hidden"
            style={{
              backgroundColor: 'var(--bg-card)',
              border: '1px solid var(--border-color)',
              boxShadow: 'var(--shadow-elevated)',
            }}
          >
            <div className="flex-1 lg:w-[60%] p-6 lg:p-8 flex flex-col">
              <div className="flex items-start gap-4 mb-4">
                <div
                  className="h-12 w-12 rounded-2xl flex items-center justify-center shrink-0"
                  style={{
                    background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
                  }}
                >
                  <ClipboardList className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h2 className="text-2xl font-bold text-[color:var(--text-primary)]">
                    Placement Test
                  </h2>
                  <p className="text-sm text-[color:var(--text-secondary)] mt-0.5">
                    Let our AI agents assess your level and build your personalized learning path
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2 mb-4">
                <span className="rounded-full bg-sky-500/20 text-sky-300 px-2.5 py-0.5 text-xs font-medium border border-sky-400/40">
                  Placement Agent
                </span>
                <span className="text-slate-500">→</span>
                <span className="rounded-full bg-violet-500/20 text-violet-300 px-2.5 py-0.5 text-xs font-medium border border-violet-400/40">
                  Exam Agent
                </span>
                <span className="text-slate-500">→</span>
                <span className="rounded-full bg-emerald-500/20 text-emerald-300 px-2.5 py-0.5 text-xs font-medium border border-emerald-400/40">
                  Analytics Agent
                </span>
              </div>

              {!placementDone ? (
                <>
                  <div className="w-full max-w-xs mb-4">
                    <label className="block text-xs font-medium text-[color:var(--text-secondary)] mb-1">
                      Track
                    </label>
                    <div className="relative">
                      <select
                        value={track}
                        onChange={(e) => setTrack(e.target.value)}
                        className="w-full appearance-none rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 pr-8"
                        style={{
                          backgroundColor: 'var(--bg-input)',
                          color: 'var(--text-primary)',
                          border: '1px solid var(--border-color)',
                        }}
                      >
                        <option value="python">Python Foundations</option>
                        <option value="deep-learning">Deep Learning</option>
                      </select>
                      <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
                    </div>
                  </div>

                  {currentQuestion ? (
                    <div
                      className="rounded-xl p-4 mb-4 border"
                      style={{
                        backgroundColor: 'var(--bg-primary)',
                        borderColor: 'var(--border-color)',
                      }}
                    >
                      <p className="text-sm font-medium text-[color:var(--text-primary)] mb-2">
                        Q{currentQuestion.order}/{currentQuestion.total}. {currentQuestion.text}
                      </p>
                      <span className="inline-block text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-300 mb-2">
                        {currentQuestion.difficulty}
                      </span>
                      <div className="space-y-1.5">
                        {currentQuestion.options.map((opt, i) => (
                          <label
                            key={i}
                            className="flex items-center gap-2 text-sm cursor-pointer"
                            style={{ color: 'var(--text-primary)' }}
                          >
                            <input
                              type="radio"
                              name="placement-q"
                              value={i}
                              checked={selectedOption === i}
                              onChange={() => setSelectedOption(i)}
                            />
                            {opt}
                          </label>
                        ))}
                      </div>
                      <button
                        type="button"
                        onClick={submitPlacement}
                        disabled={placementLoading || selectedOption === null}
                        className="mt-3 w-full rounded-xl py-2.5 px-4 text-sm font-semibold text-white flex items-center justify-center gap-2 disabled:opacity-60"
                        style={{
                          background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})`,
                        }}
                      >
                        {placementLoading ? '...' : currentQuestion.order === currentQuestion.total ? 'Finish' : 'Next'}
                        <ArrowRight className="h-4 w-4" />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={startPlacement}
                      disabled={placementLoading}
                      className="w-full max-w-xs rounded-xl py-3 px-4 text-sm font-semibold text-white flex items-center justify-center gap-2 bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] disabled:opacity-60"
                    >
                      Start Placement Test
                      <ArrowRight className="h-4 w-4" />
                    </button>
                  )}

                  {placementError && (
                    <p className="text-sm text-rose-500 mt-2">{placementError}</p>
                  )}

                  {placementDone && placementResult && (
                    <div className="mt-3 rounded-xl border border-emerald-500/40 bg-emerald-900/20 px-4 py-3 flex items-center gap-2 text-emerald-200">
                      <CheckCircle className="h-5 w-5 shrink-0" />
                      <span className="font-medium">
                        {placementResult.track} · {placementResult.level.toUpperCase()} · Grade{' '}
                        {(placementResult as { percentage?: number }).percentage ?? 0}/100
                      </span>
                    </div>
                  )}
                </>
              ) : placementResult && (
                <div className="rounded-xl border border-emerald-500/40 bg-emerald-900/20 px-4 py-3 flex items-center gap-2 text-emerald-200">
                  <CheckCircle className="h-5 w-5 shrink-0" />
                  <span className="font-medium">
                    {placementResult.track} · {placementResult.level.toUpperCase()} · Grade{' '}
                    {(placementResult as { percentage?: number }).percentage ?? 0}/100
                  </span>
                </div>
              )}
            </div>

            {/* Right 40% - stepper */}
            <div
              className="lg:w-[40%] p-6 lg:p-8 border-t lg:border-t-0 lg:border-l flex flex-col justify-center"
              style={{ borderColor: 'var(--border-color)' }}
            >
              <div className="relative flex flex-col gap-6">
                {[
                  { icon: Brain, title: '10 Adaptive Questions', desc: 'Answer questions tailored to your track' },
                  { icon: Zap, title: 'AI Evaluates Your Level', desc: 'Placement & Exam agents score your answers' },
                  { icon: Map, title: 'Personalized Path Created', desc: 'Syllabus and lessons based on your level' },
                ].map((step, i) => {
                  const Icon = step.icon
                  return (
                    <div key={i} className="flex gap-4 relative">
                      {i < 2 && (
                        <div
                          className="absolute left-5 top-10 w-0.5 h-8 border-l-2 border-dashed border-slate-600"
                          style={{ top: 40 }}
                        />
                      )}
                      <div
                        className="h-10 w-10 rounded-xl flex items-center justify-center shrink-0 z-10"
                        style={{
                          background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
                        }}
                      >
                        <Icon className="h-5 w-5 text-white" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-[color:var(--text-primary)]">
                          Step {i + 1}: {step.title}
                        </p>
                        <p className="text-xs text-[color:var(--text-muted)] mt-0.5">{step.desc}</p>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </motion.section>

          {/* Bottom 3 cards - min-height 180px, larger icons */}
          <motion.div
            initial={{ y: 10, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.05 }}
            className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-5"
          >
            {/* Syllabus */}
            <div
              className="rounded-2xl min-h-[180px] p-5 flex flex-col relative overflow-hidden"
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                boxShadow: 'var(--shadow-elevated)',
              }}
            >
              <div
                className="absolute top-0 right-0 w-24 h-24 rounded-bl-full opacity-10"
                style={{ background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` }}
              />
              <span className="absolute top-3 right-3 text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-700/50 text-slate-300">
                {syllabusGenerated ? 'Ready' : 'Locked'}
              </span>
              <div className="h-14 w-14 rounded-2xl flex items-center justify-center mb-3 shrink-0 bg-gradient-to-br from-[#3B82F6] to-sky-400">
                <BookOpen className="h-7 w-7 text-white" />
              </div>
              <h3 className="text-base font-semibold text-[color:var(--text-primary)] mb-1">
                My Syllabus & Lessons
              </h3>
              <p className="text-xs text-[color:var(--text-secondary)] mb-4 flex-1">
                Personalized learning path from the Syllabus Agents.
              </p>
              <button
                type="button"
                onClick={() => {
                  if (syllabusModules.length) navigate('/dashboard/syllabus')
                  else handleGenerateSyllabus()
                }}
                disabled={syllabusLoading || (!fullPlacementResult && !syllabusModules.length)}
                className="w-full rounded-xl py-2.5 text-sm font-semibold text-white flex items-center justify-center gap-2 disabled:opacity-60"
                style={{
                  background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})`,
                }}
              >
                {syllabusLoading ? 'Generating…' : syllabusModules.length ? 'View Syllabus →' : 'Generate Syllabus'}
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>

            {/* Exams */}
            <div
              className="rounded-2xl min-h-[180px] p-5 flex flex-col relative overflow-hidden"
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                boxShadow: 'var(--shadow-elevated)',
              }}
            >
              <span className="absolute top-3 right-3 text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-700/50 text-slate-300">
                {firstExamTaken ? 'Done' : placementDone ? 'Ready' : 'Locked'}
              </span>
              <div className="h-14 w-14 rounded-2xl flex items-center justify-center mb-3 shrink-0 bg-gradient-to-br from-violet-500 to-fuchsia-500">
                <Award className="h-7 w-7 text-white" />
              </div>
              <h3 className="text-base font-semibold text-[color:var(--text-primary)] mb-1">
                Adaptive Assessments
              </h3>
              <p className="text-xs text-[color:var(--text-secondary)] mb-4 flex-1">
                Dynamic exams powered by the Exam Agent.
              </p>
              <button
                type="button"
                onClick={handlePreviewExam}
                disabled={!placementDone}
                className="w-full rounded-xl py-2.5 text-sm font-semibold text-white flex items-center justify-center gap-2 bg-gradient-to-r from-violet-500 to-fuchsia-500 disabled:opacity-60"
              >
                {!placementDone ? 'Take Placement Test →' : 'Preview Exam'}
                <ArrowRight className="h-4 w-4" />
              </button>
              {!placementDone && (
                <p className="text-[10px] text-[color:var(--text-muted)] mt-2">
                  Complete placement test first to unlock exams.
                </p>
              )}
            </div>

            {/* Analytics */}
            <div
              className="rounded-2xl min-h-[180px] p-5 flex flex-col relative overflow-hidden sm:col-span-2 xl:col-span-1"
              style={{
                backgroundColor: 'var(--bg-card)',
                border: '1px solid var(--border-color)',
                boxShadow: 'var(--shadow-elevated)',
              }}
            >
              <span className="absolute top-3 right-3 text-[10px] font-medium px-2 py-0.5 rounded-full bg-slate-700/50 text-slate-300">
                {firstExamTaken ? `${overallMastery}%` : '—'}
              </span>
              <div className="h-14 w-14 rounded-2xl flex items-center justify-center mb-3 shrink-0 bg-gradient-to-br from-cyan-400 to-emerald-400">
                <TrendingUp className="h-7 w-7 text-white" />
              </div>
              <h3 className="text-base font-semibold text-[color:var(--text-primary)] mb-1">
                Performance & Analytics
              </h3>
              <p className="text-xs text-[color:var(--text-secondary)] mb-3 flex-1">
                Real-time mastery tracking.
              </p>
              {firstExamTaken || overallMastery > 0 ? (
                <div className="w-full h-2 rounded-full bg-slate-700 overflow-hidden mb-3">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${overallMastery}%`,
                      background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})`,
                    }}
                  />
                </div>
              ) : (
                <p className="text-[10px] text-[color:var(--text-muted)] mb-3">
                  Complete your first lesson to see analytics.
                </p>
              )}
              <button
                type="button"
                onClick={() => navigate('/dashboard/analytics')}
                className="w-full rounded-xl py-2.5 text-sm font-semibold text-cyan-500 hover:bg-cyan-500/10 transition-colors"
              >
                Explore →
              </button>
            </div>
          </motion.div>
        </div>
      </div>
    </>
  )
}
