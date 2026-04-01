import { useEffect, useMemo, useState } from 'react'
import { ExternalLink, Plus, RefreshCw } from 'lucide-react'
import { useAccentTheme } from '../hooks/useAccentTheme'
import { resourcesApi, type ResourceDto } from '../services/api'

export default function DashboardResources() {
  const { accentPrimary, accentSecondary } = useAccentTheme()
  const [items, setItems] = useState<ResourceDto[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [title, setTitle] = useState('')
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const canSubmit = useMemo(() => title.trim().length >= 2 && url.trim().length >= 5, [title, url])

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await resourcesApi.list()
      setItems(data)
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to load resources')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const add = async () => {
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      const created = await resourcesApi.create({
        title: title.trim(),
        url: url.trim(),
        description: description.trim() || undefined,
      })
      setItems((prev) => [created, ...prev])
      setTitle('')
      setUrl('')
      setDescription('')
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Failed to add resource')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="w-full p-6">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <h2 className="text-xl font-semibold text-[color:var(--text-primary)]">Resources</h2>
          <p className="text-sm text-[color:var(--text-secondary)] mt-1">
            Links and materials added by you or the admin.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium hover:bg-white/10 transition-colors"
          style={{ border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div
        className="rounded-2xl p-4 mb-6"
        style={{
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
        }}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-[color:var(--text-primary)]">Add a resource</h3>
          <div
            className="h-8 w-8 rounded-xl"
            style={{ backgroundImage: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})` }}
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (e.g., Python Docs)"
            className="w-full rounded-xl px-3 py-2 text-sm bg-transparent"
            style={{ border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
          />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="URL (https://...)"
            className="w-full rounded-xl px-3 py-2 text-sm bg-transparent"
            style={{ border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
          />
          <button
            type="button"
            onClick={add}
            disabled={!canSubmit || submitting}
            className="inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
            style={{
              backgroundImage: `linear-gradient(135deg, ${accentPrimary}, ${accentSecondary})`,
            }}
          >
            <Plus className="h-4 w-4" />
            Add
          </button>
        </div>

        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)"
          className="mt-3 w-full rounded-xl px-3 py-2 text-sm bg-transparent"
          rows={3}
          style={{ border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
        />

        {error && <p className="mt-3 text-xs text-red-400">{error}</p>}
      </div>

      <div
        className="rounded-2xl overflow-hidden"
        style={{ border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-card)' }}
      >
        <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border-color)' }}>
          <p className="text-xs text-[color:var(--text-muted)]">
            {loading ? 'Loading…' : `${items.length} resource${items.length === 1 ? '' : 's'}`}
          </p>
        </div>

        <div className="divide-y" style={{ borderColor: 'var(--border-color)' }}>
          {items.map((r) => (
            <div key={r.id} className="p-4 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[color:var(--text-primary)] truncate">{r.title}</p>
                {r.description && (
                  <p className="text-xs text-[color:var(--text-secondary)] mt-1 whitespace-pre-wrap">
                    {r.description}
                  </p>
                )}
                <p className="text-xs text-[color:var(--text-muted)] mt-2 truncate">{r.url}</p>
              </div>
              <a
                href={r.url}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium hover:bg-white/10 transition-colors"
                style={{ border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
              >
                <ExternalLink className="h-4 w-4" />
                Open
              </a>
            </div>
          ))}

          {!loading && items.length === 0 && (
            <div className="p-6 text-sm text-[color:var(--text-secondary)]">No resources yet. Add the first one above.</div>
          )}
        </div>
      </div>
    </div>
  )
}

