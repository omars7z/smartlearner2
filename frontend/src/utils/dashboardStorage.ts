import type { ModuleDto, PlacementFullResult } from '../services/api'
import { getJwtSub } from './studentIdentity'
import { normalizeSyllabusModules } from './syllabusOrder'

/** Legacy keys — shared across accounts; must not be read after login. */
export const LEGACY_DASHBOARD_KEY = 'smartlearner-dashboard-state'
export const LEGACY_PLACEMENT_RESULT_KEY = 'placement_result'
export const LEGACY_CURRENT_TRACK_KEY = 'current_track'
export const LEGACY_QA_MESSAGES_KEY = 'smartlearner-qa-messages'

export function getActiveUserId(): string | null {
  const token = localStorage.getItem('smartlearner_token')
  if (!token) return null
  return getJwtSub(token)
}

export function dashboardStateKey(userId: string): string {
  return `smartlearner-dashboard-state-user-${userId}`
}

export function placementResultKey(userId: string): string {
  return `smartlearner-placement-result-user-${userId}`
}

export function currentTrackKey(userId: string): string {
  return `smartlearner-current-track-user-${userId}`
}

export function qaMessagesKey(userId: string): string {
  return `smartlearner-qa-messages-user-${userId}`
}

/** Remove old global keys that leaked state between accounts. */
export function clearLegacyUserScopedStorage(): void {
  localStorage.removeItem(LEGACY_DASHBOARD_KEY)
  localStorage.removeItem(LEGACY_PLACEMENT_RESULT_KEY)
  localStorage.removeItem(LEGACY_CURRENT_TRACK_KEY)
  localStorage.removeItem(LEGACY_QA_MESSAGES_KEY)
}

/** Call after successful login/register before entering dashboard. */
export function onAuthSessionStarted(): void {
  clearLegacyUserScopedStorage()
}

export interface PersistedDashboardState {
  placementDone: boolean
  placementResult: unknown
  fullPlacementResult: unknown
  placementId: number | null
  syllabusGenerated: boolean
  syllabusModules: ModuleDto[]
  currentLesson: unknown
  overallMastery: number
  firstExamTaken: boolean
  currentTopic: string | null
  knowledgeMap: Record<string, number>
  masteryLevel: string
  lastAnalytics: unknown
}

export function loadDashboardState(userId: string | null, defaultState: PersistedDashboardState): PersistedDashboardState {
  if (!userId) return defaultState
  try {
    const raw = localStorage.getItem(dashboardStateKey(userId))
    if (!raw) return defaultState
    const parsed = JSON.parse(raw) as Partial<PersistedDashboardState>
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

export function saveDashboardState(userId: string | null, state: PersistedDashboardState): void {
  if (!userId) return
  try {
    localStorage.setItem(dashboardStateKey(userId), JSON.stringify(state))
  } catch {
    /* quota / private mode */
  }
}

export function clearDashboardState(userId: string | null): void {
  if (!userId) return
  localStorage.removeItem(dashboardStateKey(userId))
}

export function getUserPlacementResult(): PlacementFullResult | null {
  const uid = getActiveUserId()
  if (!uid) return null
  try {
    const raw = localStorage.getItem(placementResultKey(uid))
    return raw ? (JSON.parse(raw) as PlacementFullResult) : null
  } catch {
    return null
  }
}

export function setUserPlacementResult(result: PlacementFullResult, trackFallback = 'python'): void {
  const uid = getActiveUserId()
  if (!uid) return
  try {
    localStorage.setItem(placementResultKey(uid), JSON.stringify(result))
    localStorage.setItem(currentTrackKey(uid), result.track ?? trackFallback)
  } catch {
    /* ignore */
  }
}

export function getUserCurrentTrack(): string {
  const uid = getActiveUserId()
  if (!uid) return 'python'
  return (localStorage.getItem(currentTrackKey(uid)) || 'python').toLowerCase().replace(/-/g, '_')
}

export function loadQaMessages<T>(userId: string | null): T[] {
  if (!userId) return []
  try {
    const raw = localStorage.getItem(qaMessagesKey(userId))
    if (!raw) return []
    const parsed = JSON.parse(raw) as T[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveQaMessages(userId: string | null, messages: unknown[]): void {
  if (!userId) return
  try {
    if (messages.length === 0) {
      localStorage.removeItem(qaMessagesKey(userId))
      return
    }
    localStorage.setItem(qaMessagesKey(userId), JSON.stringify(messages))
  } catch {
    /* ignore */
  }
}

export function clearQaMessages(userId: string | null): void {
  if (!userId) return
  localStorage.removeItem(qaMessagesKey(userId))
}
