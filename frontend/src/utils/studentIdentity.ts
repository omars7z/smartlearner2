/**
 * Resolve a stable student id for backend Redis / analytics.
 * - Logged in: JWT `sub` (matches FastAPI user id).
 * - Guest: persistent device id prefixed with `device_`.
 */
function base64UrlDecode(segment: string): string {
  const pad = segment.length % 4 === 0 ? '' : '='.repeat(4 - (segment.length % 4))
  const b64 = segment.replace(/-/g, '+').replace(/_/g, '/') + pad
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return new TextDecoder().decode(bytes)
}

export function getJwtSub(token: string): string | null {
  try {
    const parts = token.split('.')
    if (parts.length < 2) return null
    const payload = JSON.parse(base64UrlDecode(parts[1])) as { sub?: string }
    return typeof payload.sub === 'string' && payload.sub.length > 0 ? payload.sub : null
  } catch {
    return null
  }
}

const DEVICE_KEY = 'smartlearner-device-id'

export function getStudentIdForApi(): string {
  const token = localStorage.getItem('smartlearner_token')
  if (token) {
    const sub = getJwtSub(token)
    if (sub) return sub
  }
  let id = localStorage.getItem(DEVICE_KEY)
  if (!id) {
    id = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `anon_${Date.now()}_${Math.random().toString(36).slice(2)}`
    localStorage.setItem(DEVICE_KEY, id)
  }
  return `device_${id}`
}
