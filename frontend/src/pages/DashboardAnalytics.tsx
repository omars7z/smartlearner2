import { useEffect, useState } from 'react'
import { BarChart2, TrendingUp, AlertTriangle, Brain, Target, Sparkles } from 'lucide-react'
import { useDashboard } from '../context/DashboardContext'
import { useAccentTheme } from '../hooks/useAccentTheme'
import { analyticsApi, type AnalyticsSummaryResponse } from '../services/api'

export default function DashboardAnalytics() {
  const { accentPrimary, accentSecondary } = useAccentTheme()
  const {
    placementDone,
    firstExamTaken,
    overallMastery,
    knowledgeMap,
    lastAnalytics,
    currentTopic,
    masteryLevel,
  } = useDashboard()
  const [agentSummary, setAgentSummary] = useState<AnalyticsSummaryResponse | null>(null)
  const [agentLoading, setAgentLoading] = useState(false)
  const [agentError, setAgentError] = useState<string | null>(null)

  const topicEntries = Object.entries(knowledgeMap).sort((a, b) => b[1] - a[1])
  const hasMap = topicEntries.length > 0
  const hasAgent = agentSummary != null
  const hasAnalytics = hasAgent || lastAnalytics != null || overallMastery > 0 || hasMap
  const insights = agentSummary?.result.insights
  const metrics = agentSummary?.result.metrics

  const riskLabel =
    lastAnalytics?.riskLevel?.replace(/^\w/, (c) => c.toUpperCase()) ??
    (firstExamTaken ? 'Low' : '—')

  useEffect(() => {
    setAgentLoading(true)
    setAgentError(null)
    analyticsApi
      .summary()
      .then((data) => setAgentSummary(data))
      .catch((err) => setAgentError(err?.response?.data?.detail || err?.message || 'Failed to load analytics'))
      .finally(() => setAgentLoading(false))
  }, [])

  return (
    <div
      className="flex-1 min-w-0 overflow-y-auto p-6"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-bold text-[color:var(--text-primary)] mb-2">
          Performance & Analytics
        </h1>
        <p className="text-sm text-[color:var(--text-muted)] mb-6">
          Adaptive analytics from placement, courses, lessons, and the Analytics Agent.
          {currentTopic && (
            <>
              {' '}
              Active topic: <code className="text-sky-400">{currentTopic}</code>
            </>
          )}
        </p>

        {agentLoading && (
          <div
            className="rounded-2xl border p-6 mb-6 text-sm text-[color:var(--text-secondary)]"
            style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
          >
            Loading Analytics Agent summary...
          </div>
        )}

        {agentError && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 mb-6 text-sm text-rose-200">
            {agentError}
          </div>
        )}

        {!hasAnalytics && !agentLoading && (
          <div
            className="rounded-2xl border-2 border-dashed p-12 text-center"
            style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-card)' }}
          >
            <BarChart2 className="h-14 w-14 mx-auto text-slate-500 mb-4" />
            <p className="text-[color:var(--text-secondary)] mb-2">
              Ask a question in <strong>Q&A</strong> with a <code className="text-xs">current_topic</code> to start
              tracking, or complete placement to seed topics.
            </p>
            <p className="text-xs text-[color:var(--text-muted)]">Level: {masteryLevel}</p>
          </div>
        )}

        {hasAnalytics && (
          <div className="space-y-6">
            {insights && (
              <div
                className="rounded-2xl p-6"
                style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
              >
                <h2 className="text-lg font-semibold text-[color:var(--text-primary)] mb-3 flex items-center gap-2">
                  <Sparkles className="h-5 w-5" />
                  Analytics Agent Insight
                </h2>
                <p className="text-sm text-[color:var(--text-secondary)] leading-relaxed mb-4">{insights.summary}</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs uppercase text-[color:var(--text-muted)] mb-2">Strengths</p>
                    <ul className="space-y-2">
                      {insights.strengths.length ? insights.strengths.slice(0, 4).map((s) => (
                        <li key={s.concept} className="text-sm text-emerald-300">
                          {s.concept}
                          <span className="block text-xs text-[color:var(--text-muted)]">{s.evidence}</span>
                        </li>
                      )) : <li className="text-sm text-[color:var(--text-muted)]">No strengths detected yet.</li>}
                    </ul>
                  </div>
                  <div>
                    <p className="text-xs uppercase text-[color:var(--text-muted)] mb-2">Needs Focus</p>
                    <ul className="space-y-2">
                      {insights.weaknesses.length ? insights.weaknesses.slice(0, 4).map((w) => (
                        <li key={w.concept} className="text-sm text-amber-300">
                          {w.concept}
                          <span className="block text-xs text-[color:var(--text-muted)]">{w.evidence}</span>
                        </li>
                      )) : <li className="text-sm text-[color:var(--text-muted)]">No weak topics detected yet.</li>}
                    </ul>
                  </div>
                </div>
                <div className="mt-5 rounded-xl p-4 bg-white/5 border border-white/10">
                  <p className="text-xs uppercase text-[color:var(--text-muted)] mb-1">Next Best Lesson</p>
                  <p className="text-sm font-semibold text-[color:var(--text-primary)]">{insights.next_best_lesson.topic}</p>
                  <p className="text-xs text-[color:var(--text-secondary)] mt-1">{insights.next_best_lesson.reason}</p>
                </div>
              </div>
            )}

            <div
              className="rounded-2xl p-6"
              style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
            >
              <h2 className="text-lg font-semibold text-[color:var(--text-primary)] mb-4 flex items-center gap-2">
                <Brain className="h-5 w-5" />
                Overall mastery
              </h2>
              <div className="flex items-center gap-4">
                <div className="flex-1 h-6 rounded-full bg-slate-700 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${metrics ? Math.round((metrics.placement_percentage ?? overallMastery)) : overallMastery}%`,
                      background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})`,
                    }}
                  />
                </div>
                <span className="text-xl font-bold text-[color:var(--text-primary)] w-16 text-right">
                  {metrics ? `${metrics.placement_percentage ?? overallMastery}%` : `${overallMastery.toFixed(0)}%`}
                </span>
              </div>
              {lastAnalytics && (
                <p className="text-xs text-[color:var(--text-muted)] mt-3">
                  Last update: {new Date(lastAnalytics.updatedAt).toLocaleString()} · Next:{' '}
                  <code>{lastAnalytics.nextAction}</code>
                </p>
              )}
            </div>

            {hasMap && (
              <div
                className="rounded-2xl p-6"
                style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
              >
                <h2 className="text-lg font-semibold text-[color:var(--text-primary)] mb-4 flex items-center gap-2">
                  <Target className="h-5 w-5" />
                  Knowledge map (topics)
                </h2>
                <ul className="space-y-3">
                  {topicEntries.map(([topic, score]) => (
                    <li key={topic}>
                      <div className="flex justify-between text-xs text-[color:var(--text-secondary)] mb-1">
                        <span className="font-mono truncate max-w-[70%]">{topic}</span>
                        <span>{(score * 100).toFixed(0)}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-slate-700 overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.min(100, Math.max(0, score * 100))}%`,
                            background: `linear-gradient(90deg, ${accentPrimary}, ${accentSecondary})`,
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div
                className="rounded-2xl p-4 flex items-center gap-3"
                style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
              >
                <div
                  className="h-12 w-12 rounded-xl flex items-center justify-center"
                  style={{ background: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` }}
                >
                  <TrendingUp className="h-6 w-6 text-white" />
                </div>
                <div>
                  <p className="text-xs text-[color:var(--text-muted)]">Placement</p>
                  <p className="text-lg font-semibold text-[color:var(--text-primary)]">
                    {metrics?.has_placement ? metrics.placement_level ?? 'Done' : placementDone ? 'Done' : '—'}
                  </p>
                </div>
              </div>
              <div
                className="rounded-2xl p-4 flex items-center gap-3"
                style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
              >
                <div className="h-12 w-12 rounded-xl flex items-center justify-center bg-amber-500/20 text-amber-400">
                  <AlertTriangle className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-xs text-[color:var(--text-muted)]">Risk</p>
                  <p className="text-lg font-semibold text-[color:var(--text-primary)]">
                    {insights
                      ? insights.risk_level
                      : lastAnalytics != null
                      ? `${(lastAnalytics.riskScore * 100).toFixed(0)}% (${riskLabel})`
                      : firstExamTaken
                        ? '—'
                        : '—'}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
