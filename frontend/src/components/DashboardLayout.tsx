import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  GraduationCap,
  Home,
  ClipboardList,
  BookOpen,
  PlayCircle,
  MessageCircle,
  FolderOpen,
  Award,
  BarChart2,
  Settings,
  LogOut,
  Bell,
  Sun,
  Moon,
  Palette,
  Check,
} from 'lucide-react'
import { useTheme } from '../context/ThemeContext'
import { useAccentTheme } from '../hooks/useAccentTheme'
import { useDashboard } from '../context/DashboardContext'

const STEPPER_STEPS = [
  { key: 'placement', label: 'Placement', path: '/dashboard/placement' },
  { key: 'syllabus', label: 'Syllabus', path: '/dashboard/syllabus' },
  { key: 'lessons', label: 'Lessons', path: '/dashboard/lessons' },
  { key: 'exams', label: 'Exams', path: '/dashboard/exams' },
  { key: 'analytics', label: 'Analytics', path: '/dashboard/analytics' },
]

const NAV_ITEMS = [
  { to: '/dashboard', end: true, label: 'Home', icon: Home },
  { to: '/dashboard/placement', end: false, label: 'Placement Test', icon: ClipboardList },
  { to: '/dashboard/syllabus', end: false, label: 'My Syllabus', icon: BookOpen },
  { to: '/dashboard/lessons', end: false, label: 'Lessons', icon: PlayCircle },
  { to: '/dashboard/qa', end: false, label: 'Q&A Assistant', icon: MessageCircle },
  { to: '/dashboard/exams', end: false, label: 'Exams', icon: Award },
  { to: '/dashboard/resources', end: false, label: 'Resources', icon: FolderOpen },
  { to: '/dashboard/analytics', end: false, label: 'Analytics', icon: BarChart2 },
  { to: '/dashboard/settings', end: false, label: 'Settings', icon: Settings },
]

export default function DashboardLayout() {
  const { theme, toggleTheme } = useTheme()
  const { accentPrimary, accentSecondary, setAccent, options } = useAccentTheme()
  const navigate = useNavigate()
  const [showAccentPicker, setShowAccentPicker] = useState(false)

  const {
    placementDone,
    syllabusGenerated,
    syllabusModules,
    currentLesson,
    firstExamTaken,
  } = useDashboard()

  const stepperDone = (key: string) => {
    if (key === 'placement') return placementDone
    if (key === 'syllabus') return syllabusGenerated && syllabusModules.length > 0
    if (key === 'lessons') return !!currentLesson || syllabusGenerated
    if (key === 'exams') return firstExamTaken
    if (key === 'analytics') return firstExamTaken
    return false
  }

  let user: { fullName?: string; email?: string; role?: 'student' | 'admin' } = { fullName: 'Student' }
  try {
    const raw = localStorage.getItem('smartlearner-current-user')
    if (raw) user = JSON.parse(raw)
  } catch (_) {}
  const isAdmin = user?.role === 'admin'
  const visibleNavItems = NAV_ITEMS.filter((i) => (i.to === '/dashboard/resources' ? isAdmin : true))

  const handleLogout = () => {
    localStorage.removeItem('smartlearner-current-user')
    localStorage.removeItem('smartlearner_token')
    navigate('/')
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="bg-dot-grid text-white"
      style={{ height: '100vh', width: '100vw', overflow: 'hidden' }}
    >
      <div className="flex" style={{ height: '100vh', width: '100vw', overflow: 'hidden' }}>
        {/* Sidebar */}
        <aside
          className="w-64 shrink-0 px-4 py-5"
          style={{
            backgroundColor: 'var(--bg-secondary)',
            borderRight: '1px solid var(--border-color)',
            height: '100vh',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <div style={{ flexShrink: 0 }}>
            <div className="flex items-center gap-2 mb-8 px-2">
              <div
                className="inline-flex items-center justify-center rounded-xl p-2.5"
                style={{
                  backgroundImage: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
                }}
              >
                <GraduationCap className="h-6 w-6 text-white" />
              </div>
              <span className="text-lg font-semibold bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] bg-clip-text text-transparent">
                SmartLearner
              </span>
            </div>

            <div className="flex items-center gap-3 mb-8 px-2">
              <div
                className="h-11 w-11 rounded-2xl flex items-center justify-center text-sm font-semibold"
                style={{
                  backgroundImage: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
                }}
              >
                {user?.fullName
                  ? user.fullName
                      .split(' ')
                      .filter(Boolean)
                      .slice(0, 2)
                      .map((n) => n[0])
                      .join('')
                  : 'MN'}
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {user?.fullName ?? 'Student'}
                </span>
                <span className="mt-1 inline-flex items-center rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-[#E5E7EB] border border-white/10">
                  Student
                </span>
              </div>
            </div>

            <nav
              className="space-y-1 text-sm"
              style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', paddingBottom: 8 }}
            >
              {visibleNavItems.map((item) => {
                const Icon = item.icon
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      `group flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left transition-all ${
                        isActive
                          ? 'text-white shadow-md'
                          : 'text-slate-700 dark:text-slate-300 hover:bg-white/10 hover:text-white'
                      }`
                    }
                    style={({ isActive }) =>
                      isActive
                        ? {
                            backgroundImage: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
                          }
                        : undefined
                    }
                  >
                    <Icon className="h-4 w-4" />
                    <span className="text-xs font-medium">{item.label}</span>
                  </NavLink>
                )
              })}
            </nav>
          </div>

          <div
            style={{
              marginTop: 'auto',
              paddingTop: 16,
              paddingBottom: 8,
              borderTop: '1px solid rgba(148,163,184,0.35)',
            }}
          >
            <button
              type="button"
              onClick={handleLogout}
              className="flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium text-slate-600 dark:text-slate-300 hover:bg-white/10 hover:text-white transition-colors w-full"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </button>
          </div>
        </aside>

        {/* Main */}
        <main
          className="flex-1 min-w-0 flex flex-col"
          style={{ height: '100vh', overflow: 'hidden' }}
        >
          <header
            className="flex items-center justify-between px-6 py-4 shrink-0"
            style={{
              backgroundColor: 'var(--bg-card)',
              borderBottom: '1px solid var(--border-color)',
            }}
          >
            <div>
              <p className="text-xs uppercase tracking-wide text-[color:var(--text-muted)]">
                Dashboard
              </p>
              <h1 className="text-xl sm:text-2xl font-semibold text-[color:var(--text-primary)]">
                Welcome back, {user?.fullName?.split(' ')[0] ?? 'Student'}{' '}
                <span aria-hidden="true">👋</span>
              </h1>
            </div>

            {/* Stepper - clickable */}
            <div className="hidden lg:flex items-center gap-2 text-[11px]">
              {STEPPER_STEPS.map((step, index) => {
                const done = stepperDone(step.key)
                return (
                  <div key={step.key} className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => navigate(step.path)}
                      className="flex items-center gap-1.5 rounded-lg px-2 py-1 hover:bg-white/10 transition-colors"
                    >
                      <div
                        className={`flex h-6 w-6 items-center justify-center rounded-full border text-[10px] transition-all ${
                          done
                            ? 'border-emerald-500 bg-emerald-500 text-white'
                            : 'border-slate-600 bg-slate-800 text-slate-300'
                        }`}
                      >
                        {done ? <Check className="h-3 w-3" /> : index + 1}
                      </div>
                      <span className="text-[color:var(--text-secondary)]">{step.label}</span>
                    </button>
                    {index < STEPPER_STEPS.length - 1 && (
                      <span className="h-px w-3 bg-slate-600/60" />
                    )}
                  </div>
                )
              })}
            </div>

            <div className="flex items-center gap-2 relative">
              <button
                type="button"
                className="relative rounded-full p-2 text-slate-500 dark:text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
              >
                <Bell className="h-4 w-4" />
                <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-[#F97316]" />
              </button>
              <button
                type="button"
                onClick={toggleTheme}
                className="rounded-full p-2 text-slate-500 dark:text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
              >
                {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
              <button
                type="button"
                onClick={() => setShowAccentPicker((v) => !v)}
                className="rounded-full p-2 text-slate-500 dark:text-slate-300 hover:text-white hover:bg-white/10 transition-colors"
                aria-label="Choose accent color"
              >
                <Palette className="h-4 w-4" />
              </button>
              <div
                className="h-8 w-8 rounded-full flex items-center justify-center text-xs font-semibold text-white"
                style={{
                  backgroundImage: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
                }}
              >
                {user?.fullName
                  ? user.fullName
                      .split(' ')
                      .filter(Boolean)
                      .slice(0, 2)
                      .map((n) => n[0])
                      .join('')
                  : 'MN'}
              </div>

              {showAccentPicker && (
                <div
                  className="absolute right-0 top-12 z-20 rounded-2xl p-3 shadow-xl grid grid-cols-6 gap-2"
                  style={{
                    backgroundColor: 'var(--bg-card)',
                    border: '1px solid var(--border-color)',
                  }}
                >
                  {(
                    [
                      ['ocean', '#3B82F6'],
                      ['cyan', '#06B6D4'],
                      ['violet', '#8B5CF6'],
                      ['rose', '#F43F5E'],
                      ['emerald', '#10B981'],
                      ['amber', '#F59E0B'],
                      ['coral', '#F97316'],
                      ['magenta', '#EC4899'],
                      ['indigo', '#6366F1'],
                      ['lime', '#84CC16'],
                      ['sky', '#38BDF8'],
                      ['slate', '#64748B'],
                    ] as [keyof typeof options, string][]
                  ).map(([key, color]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => {
                        setAccent(key)
                        setShowAccentPicker(false)
                      }}
                      className="h-7 w-7 rounded-full border-2 border-transparent hover:scale-105 transition-transform"
                      style={{
                        backgroundColor: color,
                        boxShadow: '0 0 0 1px rgba(0,0,0,0.1)',
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          </header>

          <div className="flex-1 min-h-0 flex" style={{ overflowY: 'auto' }}>
            <Outlet />
          </div>
        </main>
      </div>
    </motion.div>
  )
}
