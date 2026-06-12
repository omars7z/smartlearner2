import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../services/api'
import {
  applyGroqLimitsFromJson,
  getGroqRateLimitsSnapshot,
  subscribeGroqRateLimits,
  type GroqRateLimitState,
} from '../lib/groqRateLimitsStore'

const RateLimitContext = createContext<GroqRateLimitState | null>(null)

export function RateLimitProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<GroqRateLimitState>(() => getGroqRateLimitsSnapshot())

  useEffect(() => subscribeGroqRateLimits(() => setState(getGroqRateLimitsSnapshot())), [])

  const refresh = useCallback(async () => {
    const token = localStorage.getItem('smartlearner_token')
    if (!token) return
    try {
      const res = await api.get<Record<string, unknown>>('/usage/rate-limits')
      applyGroqLimitsFromJson(res.data)
    } catch {
      /*ignore*/
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo(() => state, [state])

  return <RateLimitContext.Provider value={value}>{children}</RateLimitContext.Provider>
}

export function useGroqRateLimits(): GroqRateLimitState {
  const ctx = useContext(RateLimitContext)
  if (!ctx) return getGroqRateLimitsSnapshot()
  return ctx
}
