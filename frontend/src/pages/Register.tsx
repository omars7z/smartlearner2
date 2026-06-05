import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { GraduationCap, Mail, Lock, User, Eye, EyeOff } from 'lucide-react'
import { useLanguage } from '../context/LanguageContext'
import { authApi } from '../services/api'
import { onAuthSessionStarted } from '../utils/dashboardStorage'

export default function Register() {
  const { t } = useLanguage()
  const navigate = useNavigate()
  const [showPassword, setShowPassword] = useState(false)
  const [showToast, setShowToast] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [form, setForm] = useState({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
    terms: false,
  })

  const passwordStrength = Math.min(
    100,
    (form.password.length > 0 ? 20 : 0) +
      (/\d/.test(form.password) ? 20 : 0) +
      (/[A-Z]/.test(form.password) ? 20 : 0) +
      (/[^a-zA-Z0-9]/.test(form.password) ? 20 : 0) +
      (form.password.length >= 8 ? 20 : 0)
  )

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (!form.fullName || !form.email || !form.password || !form.confirmPassword) {
      setError('Please fill in all fields.')
      return
    }
    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    if (!form.terms) {
      setError('You must agree to the Terms & Conditions.')
      return
    }

    try {
      const res = await authApi.register({
        fullName: form.fullName,
        email: form.email,
        password: form.password,
      })
      localStorage.setItem('smartlearner_token', res.access_token)
      localStorage.setItem(
        'smartlearner-current-user',
        JSON.stringify({
          fullName: res.full_name ?? form.fullName,
          email: res.email ?? form.email,
          role: res.role ?? 'student',
        })
      )
      onAuthSessionStarted()
      setShowToast(true)
      setTimeout(() => {
        setShowToast(false)
        navigate('/dashboard')
      }, 1500)
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Registration failed. Please try again.'
      setError(String(msg))
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen relative overflow-hidden flex items-center justify-center p-4 py-12"
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
              {t.register.title}
            </h1>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                {t.register.fullName}
              </label>
              <div className="relative">
                <User className="absolute start-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  type="text"
                  value={form.fullName}
                  onChange={(e) => setForm((f) => ({ ...f, fullName: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 py-3 ps-10 pe-4 text-slate-900 dark:text-white placeholder-slate-400 focus:border-[#3B82F6] focus:ring-2 focus:ring-[#3B82F6]/20 outline-none transition"
                  placeholder="John Doe"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                {t.register.email}
              </label>
              <div className="relative">
                <Mail className="absolute start-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 py-3 ps-10 pe-4 text-slate-900 dark:text-white placeholder-slate-400 focus:border-[#3B82F6] focus:ring-2 focus:ring-[#3B82F6]/20 outline-none transition"
                  placeholder="you@example.com"
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                {t.register.password}
              </label>
              <div className="relative">
                <Lock className="absolute start-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
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
              <div className="mt-1.5 h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-600 overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-amber-500 to-emerald-500"
                  initial={{ width: 0 }}
                  animate={{ width: `${passwordStrength}%` }}
                  transition={{ duration: 0.3 }}
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                {t.register.confirmPassword}
              </label>
              <div className="relative">
                <Lock className="absolute start-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={form.confirmPassword}
                  onChange={(e) => setForm((f) => ({ ...f, confirmPassword: e.target.value }))}
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 py-3 ps-10 pe-4 text-slate-900 dark:text-white placeholder-slate-400 focus:border-[#3B82F6] focus:ring-2 focus:ring-[#3B82F6]/20 outline-none transition"
                  placeholder="••••••••"
                />
              </div>
            </div>
            <div className="flex items-start">
              <input
                type="checkbox"
                id="terms"
                checked={form.terms}
                onChange={(e) => setForm((f) => ({ ...f, terms: e.target.checked }))}
                className="mt-1 rounded border-slate-300 text-[#3B82F6] focus:ring-[#3B82F6]"
              />
              <label htmlFor="terms" className="ms-2 text-sm text-slate-600 dark:text-slate-400">
                {t.register.terms}
              </label>
            </div>
            <button
              type="submit"
              className="w-full rounded-xl bg-gradient-to-r from-[#3B82F6] to-[#06B6D4] py-3.5 font-semibold text-white shadow-lg hover:shadow-xl hover:scale-[1.02] transition-all"
            >
              {t.register.submit}
            </button>
          </form>

          {error && (
            <p className="mt-3 text-sm text-rose-500">
              {error}
            </p>
          )}

          <p className="mt-6 text-center text-sm text-slate-600 dark:text-slate-400">
            {t.register.haveAccount}{' '}
            <Link to="/login" className="font-medium text-[#3B82F6] hover:text-[#06B6D4]">
              {t.register.login}
            </Link>
          </p>
        </div>
      </motion.div>

      {showToast && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          className="fixed bottom-8 start-1/2 -translate-x-1/2 px-6 py-3 rounded-xl bg-emerald-600 text-white font-medium shadow-lg z-50"
        >
          {t.register.success}
        </motion.div>
      )}
    </motion.div>
  )
}
