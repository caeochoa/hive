import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchWorkers } from '../api'
import type { WorkerSummary } from '../types'

export default function WorkerList() {
  const [workers, setWorkers] = useState<WorkerSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchWorkers()
      .then(setWorkers)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div
      data-theme="terminal-dark"
      className="min-h-screen bg-[--bg] p-6"
      style={{ '--bg': '#0d1117' } as React.CSSProperties}
    >
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-[--text] [--text:#e6edf3]">
          🐝 Hive
        </h1>
        <p className="text-sm text-[--text-muted] [--text-muted:#8b949e]">
          {workers.length} worker{workers.length !== 1 ? 's' : ''} registered
        </p>
      </header>

      {loading && (
        <p className="text-[--text-muted] [--text-muted:#8b949e]">Loading...</p>
      )}
      {error && (
        <p className="text-red-400">{error}</p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {workers.map(w => (
          <Link
            key={w.name}
            to={`/workers/${encodeURIComponent(w.name)}`}
            className="block rounded-xl border border-[--border] bg-[--surface] p-5
                       hover:border-[--accent] transition-colors min-h-[44px]
                       [--border:#30363d] [--surface:#161b22] [--accent:#58a6ff]"
          >
            <div className="font-semibold text-[--text] text-lg [--text:#e6edf3]">
              {w.name}
            </div>
            <div className="text-sm text-[--text-muted] mt-1 [--text-muted:#8b949e]">
              {w.cell_count} cell{w.cell_count !== 1 ? 's' : ''}
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
