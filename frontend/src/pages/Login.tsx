import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { GraduationCap, Mail, Lock, Eye, EyeOff } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { authApi } from '../services/api'

export default function Login() {
  const { t } = useLanguage()
  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    try {
      const res = await authApi.login({ email, password })
      localStorage.setItem('smartlearner_token', res.access_token)
      localStorage.setItem(
        'smartlearner-current-user',
        JSON.stringify({ fullName: res.full_name, email: res.email, role: res.role })
      )
      navigate('/dashboard')
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Invalid email or password.'
      setError(String(msg))
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen relative overflow-hidden flex items-center justify-center p-4"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-[#0F172A] via-[#1e3a5f] to-[#0F172A]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_30%_20%,rgba(59,130,246,0.15)_0%,transparent_50%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_70%_80%,rgba(6,182,212,0.1)_0%,transparent_50%)]" />
      <div className="absolute top-20 left-20 w-64 h-64 rounded-full bg-[#3B82F6]/10 blur-3xl" />
      <div className="absolute bottom-20 right-20 w-80 h-80 rounded-full bg-[#06B6D4]/10 blur-3xl" />

      <motion.div
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ delay: 0.2 }}
        className="relative w-full max-w-md"
      >
        <div className="glass-card rounded-3xl p-8 shadow-2xl">
          <div className="text-center mb-8">
            <Link to="/" className="inline-flex items-center gap-2 mb-6">
              <GraduationCap className="h-10 w-10 text-[#3B82F6]" />
              <span className="bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] bg-clip-text text-2xl font-bold text-transparent">
                SmartLearner
              </span>
            </Link>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
              {t.login.title}
            </h1>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                {t.login.email}
              </label>
              <div className="relative">
                <Mail className="absolute start-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 py-3 ps-10 pe-4 text-slate-900 dark:text-white placeholder-slate-400 focus:border-[#3B82F6] focus:ring-2 focus:ring-[#3B82F6]/20 outline-none transition"
                  placeholder="you@example.com"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                {t.login.password}
              </label>
              <div className="relative">
                <Lock className="absolute start-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 py-3 ps-10 pe-12 text-slate-900 dark:text-white placeholder-slate-400 focus:border-[#3B82F6] focus:ring-2 focus:ring-[#3B82F6]/20 outline-none transition"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute end-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              </div>
            </div>
            <div className="flex items-center">
              <input
                type="checkbox"
                id="remember"
                className="rounded border-slate-300 text-[#3B82F6] focus:ring-[#3B82F6]"
              />
              <label htmlFor="remember" className="ms-2 text-sm text-slate-600 dark:text-slate-400">
                {t.login.remember}
              </label>
            </div>
            <button
              type="submit"
              className="w-full rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] py-3.5 font-semibold text-white shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all"
            >
              {t.login.submit}
            </button>
          </form>

          {error && (
            <p className="mt-3 text-sm text-rose-500">
              {error}
            </p>
          )}

          <div className="my-6 flex items-center gap-4">
            <div className="flex-1 h-px bg-slate-200 dark:bg-slate-600" />
            <span className="text-sm text-slate-500">{t.login.or}</span>
            <div className="flex-1 h-px bg-slate-200 dark:bg-slate-600" />
          </div>

          <button
            type="button"
            className="w-full flex items-center justify-center gap-2 rounded-xl border border-slate-200 dark:border-slate-600 py-3 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            {t.login.google}
          </button>

          <p className="mt-6 text-center text-sm text-slate-600 dark:text-slate-400">
            {t.login.noAccount}{' '}
            <Link to="/register" className="font-medium text-[#3B82F6] hover:text-[#06B6D4]">
              {t.login.register}
            </Link>
          </p>
        </div>
      </motion.div>
    </motion.div>
  )
}
