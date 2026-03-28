import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut, Sun, Moon } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'

const AVATAR_COLORS = [
  '#3B82F6', '#06B6D4', '#8B5CF6', '#F43F5E', '#10B981', '#F59E0B',
  '#F97316', '#EC4899', '#6366F1', '#84CC16', '#38BDF8', '#64748B',
]

export default function DashboardSettings() {
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [user, setUser] = useState<{ fullName?: string; email?: string }>({})
  const [avatarColor, setAvatarColor] = useState(AVATAR_COLORS[0])

  useEffect(() => {
    try {
      const raw = localStorage.getItem('smartlearner-current-user')
      if (raw) setUser(JSON.parse(raw))
    } catch (_) {}
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('smartlearner-current-user')
    localStorage.removeItem('smartlearner_token')
    navigate('/')
  }

  return (
    <div
      className="flex-1 min-w-0 overflow-y-auto p-6"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <div className="max-w-xl mx-auto">
        <h1 className="text-2xl font-bold text-[color:var(--text-primary)] mb-6">Settings</h1>

        <div
          className="rounded-2xl p-6 mb-6"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
        >
          <h2 className="text-sm font-semibold text-[color:var(--text-primary)] mb-4">
            Profile
          </h2>
          <div className="flex items-center gap-4 mb-6">
            <div
              className="h-16 w-16 rounded-2xl flex items-center justify-center text-xl font-bold text-white shrink-0"
              style={{ backgroundColor: avatarColor }}
            >
              {user?.fullName
                ? user.fullName
                    .split(' ')
                    .filter(Boolean)
                    .slice(0, 2)
                    .map((n) => n[0])
                    .join('')
                : '?'}
            </div>
            <div className="flex flex-wrap gap-2">
              {AVATAR_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setAvatarColor(c)}
                  className="h-6 w-6 rounded-full border-2 transition-transform hover:scale-110"
                  style={{
                    backgroundColor: c,
                    borderColor: avatarColor === c ? '#fff' : 'transparent',
                  }}
                />
              ))}
            </div>
          </div>
          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                Full name
              </label>
              <input
                type="text"
                readOnly
                value={user?.fullName ?? ''}
                className="w-full rounded-xl px-3 py-2 text-sm bg-slate-800/50 text-[color:var(--text-primary)] border border-[var(--border-color)]"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[color:var(--text-muted)] mb-1">
                Email
              </label>
              <input
                type="email"
                readOnly
                value={user?.email ?? ''}
                className="w-full rounded-xl px-3 py-2 text-sm bg-slate-800/50 text-[color:var(--text-primary)] border border-[var(--border-color)]"
              />
            </div>
          </div>
        </div>

        <div
          className="rounded-2xl p-6 mb-6"
          style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)' }}
        >
          <h2 className="text-sm font-semibold text-[color:var(--text-primary)] mb-4">
            Preferences
          </h2>
          <div className="flex items-center justify-between">
            <span className="text-sm text-[color:var(--text-secondary)]">Theme</span>
            <button
              type="button"
              onClick={toggleTheme}
              className="flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium bg-slate-800/50 text-[color:var(--text-primary)] border border-[var(--border-color)]"
            >
              {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
          <p className="text-xs text-[color:var(--text-muted)] mt-2">
            Notification preferences can be added here.
          </p>
        </div>

        <div
          className="rounded-2xl p-6 border border-rose-500/30"
          style={{ backgroundColor: 'var(--bg-card)' }}
        >
          <h2 className="text-sm font-semibold text-rose-400 mb-2">Danger zone</h2>
          <button
            type="button"
            onClick={handleLogout}
            className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-rose-400 hover:bg-rose-500/20 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      </div>
    </div>
  )
}
