import { useEffect, useState } from 'react'
import { X, Gauge } from 'lucide-react'
import { useGroqRateLimits } from '../context/RateLimitContext'
import { hasAnyGroqLimit, liveResetSecondsRemaining } from '../lib/groqRateLimitsStore'

const DISMISS_KEY = 'smartlearner_groq_banner_dismissed'

export default function GroqRateLimitBanner() {
  const limits = useGroqRateLimits()
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(DISMISS_KEY) === '1')
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!hasAnyGroqLimit(limits)) return
    const id = window.setInterval(() => setTick((t) => t + 1), 1000)
    return () => window.clearInterval(id)
  }, [limits])

  if (dismissed || !hasAnyGroqLimit(limits)) return null

  const liveReset = liveResetSecondsRemaining(limits)
  void tick

  const parts: string[] = []
  if (limits.limitRequests != null) {
    parts.push(`RPM limit ${limits.limitRequests}`)
  }
  if (limits.remainingRequests != null) {
    parts.push(`${limits.remainingRequests} requests left this window`)
  }
  if (liveReset != null) {
    parts.push(`window resets in ~${liveReset}s`)
  } else if (limits.resetRequestsSeconds != null) {
    parts.push(`reset in ${limits.resetRequestsSeconds}s (from last response)`)
  }
  if (limits.remainingTokens != null) {
    parts.push(`~${limits.remainingTokens} tokens remaining (TPM)`)
  }

  return (
    <div
      className="shrink-0 border-t px-4 py-2 flex items-start gap-3 text-xs sm:text-sm"
      style={{
        borderColor: 'var(--border-color)',
        backgroundColor: 'var(--bg-card)',
        color: 'var(--text-secondary)',
      }}
      role="status"
      aria-live="polite"
    >
      <Gauge className="h-4 w-4 shrink-0 mt-0.5 text-amber-400" aria-hidden />
      <div className="flex-1 min-w-0">
        <span className="font-semibold text-[color:var(--text-primary)]">Groq API usage · </span>
        <span>{parts.join(' · ')}</span>
      </div>
      <button
        type="button"
        onClick={() => {
          localStorage.setItem(DISMISS_KEY, '1')
          setDismissed(true)
        }}
        className="shrink-0 p-1 rounded-lg hover:bg-white/10 text-[color:var(--text-muted)]"
        aria-label="Dismiss rate limit banner"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
