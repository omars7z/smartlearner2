import { useToast } from '../context/ToastContext'
import { CheckCircle, XCircle, Info, X } from 'lucide-react'

export function ToastContainer() {
  const { toasts, removeToast } = useToast()

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => {
        const isSuccess = t.type === 'success'
        const isError = t.type === 'error'
        const Icon = isSuccess ? CheckCircle : isError ? XCircle : Info
        return (
          <div
            key={t.id}
            className={`flex items-start gap-3 rounded-xl border px-4 py-3 shadow-lg backdrop-blur-sm ${
              isSuccess
                ? 'bg-emerald-500/10 border-emerald-400/30 text-emerald-800 dark:text-emerald-200'
                : isError
                  ? 'bg-rose-500/10 border-rose-400/30 text-rose-800 dark:text-rose-200'
                  : 'bg-sky-500/10 border-sky-400/30 text-sky-800 dark:text-sky-200'
            }`}
          >
            <Icon className="h-5 w-5 shrink-0 mt-0.5" />
            <p className="text-sm flex-1">{t.message}</p>
            <button
              type="button"
              onClick={() => removeToast(t.id)}
              className="shrink-0 p-0.5 rounded hover:bg-black/10 dark:hover:bg-white/10"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
