export type GroqRateLimitState = {
  limitRequests?: string
  remainingRequests?: string
  resetRequestsSeconds?: string
  remainingTokens?: string
  receivedAt?: number
}

const HEADER_TO_KEY: [string, keyof GroqRateLimitState][] = [
  ['x-app-ratelimit-limit-requests', 'limitRequests'],
  ['x-app-ratelimit-remaining-requests', 'remainingRequests'],
  ['x-app-ratelimit-reset-requests', 'resetRequestsSeconds'],
  ['x-app-ratelimit-remaining-tokens', 'remainingTokens'],
]

let snapshot: GroqRateLimitState = {}
const listeners = new Set<() => void>()

export function getGroqRateLimitsSnapshot(): GroqRateLimitState {
  return { ...snapshot }
}

export function subscribeGroqRateLimits(cb: () => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

function headerGet(headers: Record<string, string>, canonical: string): string | undefined {
  const want = canonical.toLowerCase()
  for (const [k, v] of Object.entries(headers)) {
    if (k.toLowerCase() === want && v != null && String(v).trim() !== '') {
      return String(v).trim()
    }
  }
  return undefined
}

/** Merge values from axios response headers (after any API call). */
export function applyGroqLimitsFromResponseHeaders(headers: Record<string, string> | undefined): void {
  if (!headers || typeof headers !== 'object') return
  let changed = false
  const next = { ...snapshot }
  const now = Date.now()
  for (const [hName, key] of HEADER_TO_KEY) {
    const v = headerGet(headers as Record<string, string>, hName)
    if (v != undefined) {
      next[key] = v
      changed = true
    }
  }
  if (changed) {
    next.receivedAt = now
    snapshot = next
    listeners.forEach((fn) => fn())
  }
}

/** Merge from GET /usage/rate-limits JSON body. */
export function applyGroqLimitsFromJson(body: Record<string, unknown> | null | undefined): void {
  if (!body || typeof body !== 'object') return
  const next = { ...snapshot }
  let changed = false
  const map: [string, keyof GroqRateLimitState][] = [
    ['limit_requests', 'limitRequests'],
    ['remaining_requests', 'remainingRequests'],
    ['reset_requests_seconds', 'resetRequestsSeconds'],
    ['remaining_tokens', 'remainingTokens'],
  ]
  for (const [jsonKey, stateKey] of map) {
    const v = body[jsonKey]
    if (v != null && String(v).trim() !== '') {
      next[stateKey] = String(v).trim()
      changed = true
    }
  }
  if (changed) {
    next.receivedAt = Date.now()
    snapshot = next
    listeners.forEach((fn) => fn())
  }
}

export function liveResetSecondsRemaining(state: GroqRateLimitState): number | null {
  const raw = state.resetRequestsSeconds
  const receivedAt = state.receivedAt
  if (raw == null || receivedAt == null) return null
  const sec = parseInt(raw, 10)
  if (!Number.isFinite(sec)) return null
  const elapsed = (Date.now() - receivedAt) / 1000
  return Math.max(0, Math.round(sec - elapsed))
}

export function hasAnyGroqLimit(state: GroqRateLimitState): boolean {
  return !!(
    state.limitRequests ||
    state.remainingRequests ||
    state.resetRequestsSeconds ||
    state.remainingTokens
  )
}
