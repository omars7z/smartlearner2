export type StoredUser = { fullName?: string; email?: string; role?: string }

export function getStoredUser(): StoredUser | null {
  try {
    const raw = localStorage.getItem('smartlearner-current-user')
    if (!raw) return null
    return JSON.parse(raw) as StoredUser
  } catch {
    return null
  }
}

export function isStoredUserAdmin(): boolean {
  const r = getStoredUser()?.role
  return String(r ?? '').toLowerCase() === 'admin'
}
