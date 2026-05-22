import type { AnalyticsPayload } from '../services/api'

export interface AgentOutput {
  student_id: string
  timestamp?: string
  student_profile?: {
    learning_speed?: number
    consistency_score?: number
    avg_quiz_score?: number
    total_interactions?: number
    adaptive_params?: Record<string, number>
  }
  mastery_state: Record<string, number>
  velocity_map?: Record<string, { velocity: number; momentum: number; trend: string; sessions_count: number }>
  weakness_flags?: { topic: string; reason: string; severity: string; signal_count?: number }[]
  progress_report?: {
    completed_topics: string[]
    in_progress_topics: string[]
    weak_topics: string[]
    mastery_summary: Record<string, number>
    overall_progress_percent: number
    recommendation: string
    next_topic: string
    topic_trends?: Record<string, string>
  }
  risk_flag?: boolean
  risk_factors?: string[]
  next_action?: string
  personal_summary?: string
  motivating_recommendations?: string[]
}

/** Convert Analytics Agent JSON into the shared AnalyticsPayload shape. */
export function agentOutputToPayload(output: AgentOutput): AnalyticsPayload {
  const mastery = output.mastery_state ?? {}
  const progress = output.progress_report
  const overall = Math.max(0, Math.min(1, (progress?.overall_progress_percent ?? 0) / 100))
  const nextTopic = progress?.next_topic ?? ''
  const riskLevel: AnalyticsPayload['risk_level'] = output.risk_flag
    ? 'high'
    : (progress?.weak_topics?.length ?? 0) > 0
      ? 'medium'
      : 'low'

  return {
    status: 'ok',
    student_id: String(output.student_id),
    mastery_update: {
      topic: nextTopic,
      new_score: nextTopic ? (mastery[nextTopic] ?? overall) : overall,
      overall_mastery: overall,
    },
    knowledge_map: { ...mastery },
    overall_mastery: overall,
    risk_score: riskLevel === 'high' ? 0.85 : riskLevel === 'medium' ? 0.5 : 0.15,
    risk_level: riskLevel,
    next_action: output.next_action ?? progress?.recommendation ?? 'continue',
    recommendations: progress?.next_topic
      ? [{ type: 'focus', message: `Next topic: ${progress.next_topic}`, priority: 'high' }]
      : [],
    milestones: [
      {
        type: 'progress',
        message: `Overall progress: ${(overall * 100).toFixed(0)}%`,
        topic: progress?.next_topic,
      },
    ],
    mastery_state: {
      overall_accuracy: overall,
      topics: { ...mastery },
      topic_trends: progress?.topic_trends,
    },
    student_profile: output.student_profile,
    velocity_map: output.velocity_map,
    risk_factors: output.risk_factors,
  }
}
