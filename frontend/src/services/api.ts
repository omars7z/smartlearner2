import axios from 'axios'
import { applyGroqLimitsFromResponseHeaders } from '../lib/groqRateLimitsStore'

/** Strip trailing slashes and accidental `/api` or `/api/v1` so we never build `.../api/v1/api/v1`. */
function normalizeViteApiOrigin(raw: string | undefined | null): string {
  if (raw == null) return ''
  let s = String(raw).trim()
  if (!s) return ''
  s = s.replace(/\/+$/, '')
  const lower = s.toLowerCase()
  if (lower.endsWith('/api/v1')) s = s.slice(0, -'/api/v1'.length).replace(/\/+$/, '')
  else if (lower.endsWith('/api')) s = s.slice(0, -'/api'.length).replace(/\/+$/, '')
  return s
}

const resolvedOrigin = normalizeViteApiOrigin(import.meta.env.VITE_API_ORIGIN as string | undefined)

/** e.g. VITE_API_ORIGIN=https://your-backend.railway.app (host only, no /api path) — same user DB when backend uses cloud DATABASE_URL */
const API_BASE =
  resolvedOrigin !== '' ? `${resolvedOrigin}/api/v1` : 'http://localhost:8000/api/v1'

export { API_BASE }

/** User-facing message for failed requests (including Axios "Network Error" when the browser blocks or the server never answers). */
export function describeApiError(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const d = err.response?.data as { detail?: unknown } | undefined
    const detail = d?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length)
      return detail.map((x) => (typeof x === 'string' ? x : JSON.stringify(x))).join('; ')
    if (!err.response && (err.code === 'ERR_NETWORK' || err.message === 'Network Error')) {
      return (
        `No response from API (${API_BASE}). ` +
        'Start the backend, check VITE_API_ORIGIN, and if the site is not on localhost set backend CORS_EXTRA_ORIGINS to this page’s origin. ' +
        'HTTPS pages cannot call http:// APIs (mixed content).'
      )
    }
    if (typeof err.message === 'string' && err.message.trim()) return err.message
  }
  if (err instanceof Error && err.message.trim()) return err.message
  return fallback
}

/** Placement runs many sequential LLM calls; default axios has no limit but proxies may still drop long requests. */
const PLACEMENT_REQUEST_MS = 180_000

export const api = axios.create({
  baseURL: API_BASE,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('smartlearner_token')
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

function headersToRecord(h: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  if (!h || typeof h !== 'object') return out
  const obj = h as Record<string, unknown>
  for (const key of Object.keys(obj)) {
    const val = obj[key]
    if (val != null && val !== '') out[key] = String(val)
  }
  return out
}

api.interceptors.response.use(
  (response) => {
    applyGroqLimitsFromResponseHeaders(headersToRecord(response.headers))
    return response
  },
  (error) => {
    if (error?.response?.headers) {
      applyGroqLimitsFromResponseHeaders(headersToRecord(error.response.headers))
    }
    if (error?.response?.status === 401) {
      localStorage.removeItem('smartlearner_token')
      localStorage.removeItem('smartlearner-current-user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export type UserRole = 'student' | 'admin'

/** Backend returns TokenResponse; profile fields are optional until /me exists. */
export interface AuthResponse {
  access_token: string
  token_type?: string
  full_name?: string
  email?: string
  role?: UserRole
}

export const authApi = {
  async register(payload: { fullName: string; email: string; password: string; role: UserRole }) {
    const res = await api.post<AuthResponse>('/auth/register', {
      full_name: payload.fullName,
      email: payload.email,
      password: payload.password,
      role: payload.role,
    })
    return res.data
  },
  async login(payload: { email: string; password: string }) {
    const res = await api.post<AuthResponse>('/auth/token', payload)
    return res.data
  },
}

/** Analytics block returned from POST /qa/ask (Phase 4 DKT + Redis). */
export interface AnalyticsPayload {
  status: string
  student_id: string
  mastery_update: {
    topic: string
    new_score: number
    overall_mastery: number
  }
  knowledge_map: Record<string, number>
  overall_mastery: number
  risk_score: number
  risk_level: 'low' | 'medium' | 'high'
  next_action: string
  recommendations: { type: string; message: string; priority?: string }[]
  milestones: { type: string; message: string; topic?: string; emoji?: string }[]
  mastery_state: {
    overall_accuracy: number
    topics: Record<string, number>
    onboarding_goals?: unknown
  }
}

export interface QAExplanationResult {
  status?: string
  rag?: Record<string, unknown>
  explanation?: Record<string, unknown>
  level?: string
  chunks_used?: number
  knowledge_context?: Record<string, unknown>
  validation?: Record<string, unknown>
  analytics?: AnalyticsPayload
  suggestions?: string[]
}

export interface QAResponse {
  status: string
  intent: string
  result: QAExplanationResult
  routing?: { steps?: string[] }
  pipeline?: string[]
}

export const qaApi = {
  async ask(question: string, currentTopic?: string, studentContext?: Record<string, unknown>) {
    const body: Record<string, unknown> = { question }
    if (currentTopic) body.current_topic = currentTopic
    if (studentContext && Object.keys(studentContext).length) {
      body.student_context = studentContext
    }
    const res = await api.post<QAResponse>('/qa/ask', body, { timeout: 90_000 })
    return res.data
  },
}

/** Save onboarding goals (Redis-backed; used by syllabus pipeline). */
export const onboardingApi = {
  async saveGoals(payload: {
    learning_goal: 'data_science' | 'web_dev' | 'automation' | 'ai' | 'general'
    hours_per_day: 0.5 | 1 | 2
    background: 'none' | 'other_language' | 'some_python'
  }) {
    const res = await api.post('/onboarding/goals', payload)
    return res.data as Record<string, unknown>
  },
}

// Placement
export interface PlacementQuestionDto {
  id: string
  order: number
  total: number
  text: string
  difficulty: string
  topic: string
  options: string[]
  level?: string
  level_label?: string
  level_index?: number
  level_stage?: number
  levels_total?: number
}

export interface StartPlacementResponse {
  status: string
  placement_id: number
  next_question: PlacementQuestionDto | null
}

export interface AnswerPlacementResponse {
  status: string
  finished: boolean
  correct?: boolean
  next_question?: PlacementQuestionDto | null
  placement_result?: PlacementFullResult
}

export interface PlacementFullResult {
  track: string
  score: number
  percentage: number
  level: string
  strong_topics: string[]
  weak_topics: string[]
  recommended_start_topic: string
  final_level?: string
  levels_passed?: string[]
  stopped_reason?: 'failed_level' | 'completed_all'
  passed_all_tiers?: boolean
  /** Correct count in the last 5-question stage (where pass/fail was decided). */
  last_block_correct?: number
  last_block_total?: number
  /** Total answers submitted across the whole placement run. */
  total_answered?: number
}

export const placementApi = {
  async start(track: string) {
    const res = await api.post<StartPlacementResponse>(
      '/placement/start',
      { track },
      { timeout: PLACEMENT_REQUEST_MS }
    )
    return res.data
  },
  async answer(placementId: number, track: string, questionId: string, answerIndex: number) {
    const res = await api.post<AnswerPlacementResponse>(
      '/placement/answer',
      {
        placement_id: placementId,
        track,
        question_id: questionId,
        answer_index: answerIndex,
      },
      { timeout: PLACEMENT_REQUEST_MS }
    )
    return res.data
  },
  async getResults() {
    const res = await api.get('/placement/results')
    return res.data
  },
}

// Syllabus
export interface LessonDto {
  lesson_id: string
  title: string
  topic: string
  topic_name?: string
  duration_minutes?: number
  order?: number
  course_id?: number
  parent_lesson_id?: number | null
  is_sub_lesson?: boolean
  sub_lessons?: LessonDto[]
}

export interface ModuleDto {
  module_id: string
  title: string
  target_level: string
  lessons: LessonDto[]
}

export interface SyllabusGenerateEnvelope {
  status: string
  intent: string
  result: {
    status: string
    track: string
    level: string
    syllabus: ModuleDto[]
    validation: {
      status: string
      is_valid: boolean
      issues: string[]
    }
  }
}

export const syllabusApi = {
  async generate(placementId: number, courseTitle?: string) {
    const res = await api.post<SyllabusGenerateEnvelope>('/syllabus/generate', {
      placement_id: placementId,
      course_title: courseTitle,
    })
    return res.data
  },
}

export interface Py4eSubLesson {
  id: string
  title: string
}

export interface Py4eChapterOutline {
  key: string
  track_id: string
  number: number
  title: string
  difficulty: string
  topics: string[]
  sub_lessons: Py4eSubLesson[]
}

export interface Py4eCurriculumPayload {
  source: string
  tracks: {
    id: string
    label_en: string
    label_ar: string
    goal_ar: string
    chapter_keys: string[]
  }[]
  chapters: Record<string, Py4eChapterOutline>
}

export const curriculumApi = {
  async getPy4e() {
    const res = await api.get<Py4eCurriculumPayload>('/curriculum/py4e')
    return res.data
  },
  async getDeepLearning() {
    const res = await api.get<Py4eCurriculumPayload>('/curriculum/deep-learning')
    return res.data
  },
}

// Lessons content (from backend / seed_content)
export interface LessonContentResponse {
  found: boolean
  title: string
  topic: string
  text: string
}

export type LessonSection =
  | { type: 'markdown'; content: string }
  | { type: 'introduction'; content: string }
  | { type: 'explanation'; title?: string; content: string; subsections?: any[] }
  | { type: 'code_example'; title?: string; code: string; explanation?: string }
  | {
      type: 'common_mistakes'
      mistakes: { description: string; wrong_code: string; correct_code: string; explanation?: string }[]
    }
  | {
      type: 'exercises'
      exercises: { title: string; difficulty: string; description: string; solution: string }[]
    }
  | { type: 'summary'; points: string[] }

export interface StructuredLesson {
  lesson_id: string
  title: string
  duration_minutes: number
  sections: LessonSection[]
  sub_lessons?: LessonDto[]
  is_parent_with_sub_lessons?: boolean
  course_id?: number
}

export interface GetLessonResponse {
  status: string
  lesson: StructuredLesson
  generated_in_ms?: number
  llm_used?: boolean
}

export const lessonsApi = {
  async getContent(topic?: string, lessonId?: string) {
    const params = new URLSearchParams()
    if (topic) params.set('topic', topic)
    if (lessonId) params.set('lesson_id', lessonId)
    const res = await api.get<LessonContentResponse>(`/lessons/content?${params.toString()}`)
    return res.data
  },
  async getLesson(lessonId: string, params?: { topic?: string; lessonTitle?: string; level?: string; durationMinutes?: number }) {
    const qs = new URLSearchParams()
    if (params?.topic) qs.set('topic', params.topic)
    if (params?.lessonTitle) qs.set('lesson_title', params.lessonTitle)
    if (params?.level) qs.set('level', params.level)
    if (params?.durationMinutes != null) qs.set('duration_minutes', String(params.durationMinutes))
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    const res = await api.get<GetLessonResponse>(`/lessons/${encodeURIComponent(lessonId)}${suffix}`, { timeout: 90_000 })
    return res.data
  },
}

// Exams
export interface ExamQuestionDto {
  id: string
  text: string
  difficulty: 'easy' | 'medium' | 'hard'
  options: string[]
  correct_answer?: string
  correct_index?: number
  question_text?: string
  question_id?: string
  explanation?: string
}

export interface ExamGenerateEnvelope {
  status: string
  intent: string
  result: {
    status: string
    lesson_id: string
    questions: ExamQuestionDto[]
  }
}

export interface ExamGradeEnvelope {
  status: string
  intent: string
  result: {
    status: string
    lesson_id: string
    overall_score: number
    difficulty_breakdown: Record<string, number>
  }
}

export const examsApi = {
  async generate(lessonId: string) {
    const res = await api.post<ExamGenerateEnvelope>('/exams/generate', { lesson_id: lessonId })
    return res.data
  },
  async grade(lessonId: string, answers: { question_id: string; answer_index: number }[]) {
    const res = await api.post<ExamGradeEnvelope>('/exams/grade', {
      lesson_id: lessonId,
      answers,
    })
    return res.data
  },
}

// Quick Assessment (DKT-linked)
export interface QuickAssessmentQuestionDto {
  id: string
  text: string
  options: string[]
}

export interface QuickAssessmentGenerateResponse {
  status: string
  lesson_id: string
  topic: string
  questions: QuickAssessmentQuestionDto[]
  llm_used?: boolean
  generated_in_ms?: number
}

export interface QuickAssessmentGradeAnswerDto {
  question_id: string
  answer_index: number
}

export interface QuickAssessmentGradeResponse {
  status: string
  lesson_id: string
  topic: string
  grading: {
    correct_count: number
    total: number
    per_question: { question_id: string; is_correct: boolean }[]
  }
  analytics?: AnalyticsPayload
  follow_up_explanation?: unknown
  next_action: string
  updated_syllabus_modules?: ModuleDto[]
}

export const quickAssessmentApi = {
  async generate(lessonId: string, topic: string, level: string) {
    const res = await api.post<QuickAssessmentGenerateResponse>('/lessons/quick-assessment/generate', {
      lesson_id: lessonId,
      topic,
      level,
    })
    return res.data
  },
  async grade(lessonId: string, topic: string, answers: QuickAssessmentGradeAnswerDto[]) {
    const res = await api.post<QuickAssessmentGradeResponse>('/lessons/quick-assessment/grade', {
      lesson_id: lessonId,
      topic,
      answers,
    })
    return res.data
  },
}

export interface AnalyticsSummaryResponse {
  status: string
  intent: string
  result: {
    course_context: {
      track: string
      course_title: string
      subject: string
      source: string
    }
    metrics: {
      student_id: number
      track: string
      course_title: string
      has_placement: boolean
      placement_id?: number | null
      placement_level?: string | null
      placement_percentage?: number | null
      total_answered: number
      strong_topics: string[]
      weak_topics: string[]
      recommended_start_topic?: string | null
      course_count: number
      lesson_count: number
      generated_lesson_count: number
      lesson_completion_rate: number
    }
    insights: {
      summary: string
      strengths: { concept: string; evidence: string }[]
      weaknesses: { concept: string; evidence: string; severity?: string }[]
      patterns: string[]
      recommendations: { priority: number; action: string; target_concept?: string }[]
      next_best_lesson: { topic: string; reason: string }
      risk_level: 'low' | 'medium' | 'high'
      confidence: 'low' | 'medium' | 'high'
    }
  }
}

export const analyticsApi = {
  async summary(track?: string) {
    const params = track ? `?track=${encodeURIComponent(track)}` : ''
    const res = await api.get<AnalyticsSummaryResponse>(`/analytics/summary${params}`, { timeout: 90_000 })
    return res.data
  },
}

// Resources
export interface ResourceDto {
  id: number
  title: string
  url: string
  description?: string | null
  created_at?: string
  created_by_user_id?: number
}

export const resourcesApi = {
  async list() {
    const res = await api.get<ResourceDto[]>('/resources')
    return res.data
  },
  async create(payload: { title: string; url: string; description?: string }) {
    const res = await api.post<ResourceDto>('/resources', payload)
    return res.data
  },
}


