import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import type { AnalyticsPayload, ModuleDto, LessonDto, PlacementFullResult } from '../services/api'
import { normalizeSyllabusModules } from '../utils/syllabusOrder'

const STORAGE_KEY = 'smartlearner-dashboard-state'

export interface DashboardPlacementResult {
  level: string
  score: number
  track: string
  percentage?: number
}

/** Last analytics snapshot from Q&A (DKT / Redis-backed). */
export interface LastAnalyticsSnapshot {
  studentId: string
  overallMastery: number
  riskScore: number
  riskLevel: string
  knowledgeMap: Record<string, number>
  nextAction: string
  updatedAt: number
}

export interface DashboardState {
  placementDone: boolean
  placementResult: DashboardPlacementResult | null
  fullPlacementResult: PlacementFullResult | null
  placementId: number | null
  syllabusGenerated: boolean
  syllabusModules: ModuleDto[]
  currentLesson: LessonDto | null
  overallMastery: number
  firstExamTaken: boolean
  /** Topic slug for Q&A + analytics (e.g. python_lists). */
  currentTopic: string | null
  /** Mastery per topic 0–1; synced with backend knowledge_map. */
  knowledgeMap: Record<string, number>
  masteryLevel: string
  lastAnalytics: LastAnalyticsSnapshot | null
}

const defaultState: DashboardState = {
  placementDone: false,
  placementResult: null,
  fullPlacementResult: null,
  placementId: null,
  syllabusGenerated: false,
  syllabusModules: [],
  currentLesson: null,
  overallMastery: 0,
  firstExamTaken: false,
  currentTopic: null,
  knowledgeMap: {},
  masteryLevel: 'beginner',
  lastAnalytics: null,
}

function loadState(): DashboardState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultState
    const parsed = JSON.parse(raw) as Partial<DashboardState>
    return {
      ...defaultState,
      ...parsed,
      placementResult: parsed.placementResult ?? defaultState.placementResult,
      fullPlacementResult: parsed.fullPlacementResult ?? defaultState.fullPlacementResult,
      syllabusModules: normalizeSyllabusModules(
        Array.isArray(parsed.syllabusModules) ? (parsed.syllabusModules as ModuleDto[]) : [],
      ),
      knowledgeMap:
        parsed.knowledgeMap && typeof parsed.knowledgeMap === 'object'
          ? (parsed.knowledgeMap as Record<string, number>)
          : {},
      currentTopic: typeof parsed.currentTopic === 'string' ? parsed.currentTopic : null,
      masteryLevel: typeof parsed.masteryLevel === 'string' ? parsed.masteryLevel : 'beginner',
      lastAnalytics: parsed.lastAnalytics ?? null,
    }
  } catch {
    return defaultState
  }
}

function saveState(state: DashboardState) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch (_) {}
}

interface DashboardContextValue extends DashboardState {
  setPlacementDone: (result: DashboardPlacementResult | null, full?: PlacementFullResult | null, placementId?: number | null) => void
  setSyllabusModules: (modules: ModuleDto[]) => void
  setCurrentLesson: (lesson: LessonDto | null) => void
  setOverallMastery: (value: number) => void
  setFirstExamTaken: (value: boolean) => void
  setCurrentTopic: (topic: string | null) => void
  setMasteryLevel: (level: string) => void
  setKnowledgeMap: (map: Record<string, number>) => void
  mergeAnalyticsFromQA: (analytics: AnalyticsPayload | undefined) => void
  resetDashboard: () => void
}

const DashboardContext = createContext<DashboardContextValue | null>(null)

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<DashboardState>(loadState)

  useEffect(() => {
    saveState(state)
  }, [state])

    const setPlacementDone = useCallback(
    (result: DashboardPlacementResult | null, full?: PlacementFullResult | null, placementId?: number | null) => {
      setState((s) => {
        const next = {
          ...s,
          placementDone: result != null,
          placementResult: result ?? null,
          fullPlacementResult: full ?? s.fullPlacementResult ?? null,
          placementId: placementId ?? s.placementId,
          syllabusGenerated: result == null ? s.syllabusGenerated : false,
          syllabusModules: result == null ? s.syllabusModules : [],
          currentLesson: result == null ? s.currentLesson : null,
          firstExamTaken: result == null ? s.firstExamTaken : false,
        }
        if (full && result != null) {
          const km: Record<string, number> = { ...next.knowledgeMap }
          for (const t of full.weak_topics) km[String(t)] = 0.0
          for (const t of full.strong_topics) km[String(t)] = 1.0
          next.knowledgeMap = km
          next.masteryLevel = (full.level || next.masteryLevel).toLowerCase()
        }
        return next
      })
    },
    []
  )

  const setSyllabusModules = useCallback((syllabusModules: ModuleDto[]) => {
    setState((s) => ({
      ...s,
      syllabusGenerated: syllabusModules.length > 0,
      syllabusModules: normalizeSyllabusModules(syllabusModules),
    }))
  }, [])

  const setCurrentLesson = useCallback((currentLesson: LessonDto | null) => {
    setState((s) => ({ ...s, currentLesson }))
  }, [])

  const setOverallMastery = useCallback((overallMastery: number) => {
    setState((s) => ({ ...s, overallMastery: Math.max(0, Math.min(100, overallMastery)) }))
  }, [])

  const setFirstExamTaken = useCallback((firstExamTaken: boolean) => {
    setState((s) => ({ ...s, firstExamTaken }))
  }, [])

  const setCurrentTopic = useCallback((currentTopic: string | null) => {
    setState((s) => ({ ...s, currentTopic }))
  }, [])

  const setMasteryLevel = useCallback((masteryLevel: string) => {
    setState((s) => ({ ...s, masteryLevel }))
  }, [])

  const setKnowledgeMap = useCallback((knowledgeMap: Record<string, number>) => {
    setState((s) => ({ ...s, knowledgeMap: { ...knowledgeMap } }))
  }, [])

  const mergeAnalyticsFromQA = useCallback((analytics: AnalyticsPayload | undefined) => {
    if (!analytics) return
    setState((s) => {
      const km = analytics.knowledge_map ?? s.knowledgeMap
      const overallPct = Math.round(Math.max(0, Math.min(1, analytics.overall_mastery ?? 0)) * 100)
      return {
        ...s,
        knowledgeMap: { ...km },
        overallMastery: overallPct,
        lastAnalytics: {
          studentId: analytics.student_id,
          overallMastery: analytics.overall_mastery ?? 0,
          riskScore: analytics.risk_score ?? 0,
          riskLevel: analytics.risk_level ?? 'low',
          knowledgeMap: { ...km },
          nextAction: analytics.next_action ?? 'continue',
          updatedAt: Date.now(),
        },
      }
    })
  }, [])

  const resetDashboard = useCallback(() => {
    setState(defaultState)
  }, [])

  const value = useMemo<DashboardContextValue>(
    () => ({
      ...state,
      setPlacementDone,
      setSyllabusModules,
      setCurrentLesson,
      setOverallMastery,
      setFirstExamTaken,
      setCurrentTopic,
      setMasteryLevel,
      setKnowledgeMap,
      mergeAnalyticsFromQA,
      resetDashboard,
    }),
    [
      state,
      setPlacementDone,
      setSyllabusModules,
      setCurrentLesson,
      setOverallMastery,
      setFirstExamTaken,
      setCurrentTopic,
      setMasteryLevel,
      setKnowledgeMap,
      mergeAnalyticsFromQA,
      resetDashboard,
    ]
  )

  return (
    <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>
  )
}

export function useDashboard() {
  const ctx = useContext(DashboardContext)
  if (!ctx) throw new Error('useDashboard must be used within DashboardProvider')
  return ctx
}
