import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchWorkerDetail } from '../api'
import type { WorkerDetail, CellMeta, ThemeName } from '../types'
import ExpandModal from '../components/ExpandModal'
import MetricCell from '../components/cells/MetricCell'
import StatusCell from '../components/cells/StatusCell'
import FileCell from '../components/cells/FileCell'
import TableCell from '../components/cells/TableCell'
import ChartCell from '../components/cells/ChartCell'
import LogCell from '../components/cells/LogCell'
import AppCell from '../components/cells/AppCell'

function CellDispatch({
  cell, workerName, theme, onExpand,
}: {
  cell: CellMeta
  workerName: string
  theme: ThemeName
  onExpand: () => void
}) {
  const props = { workerName, index: cell.index, title: cell.title, onExpand }
  switch (cell.type) {
    case 'metric':   return <MetricCell {...props} />
    case 'status':   return <StatusCell {...props} />
    case 'file':
    case 'markdown': return <FileCell {...props} />
    case 'table':    return <TableCell {...props} />
    case 'chart':    return <ChartCell {...props} />
    case 'log':      return <LogCell {...props} />
    case 'app':
      return <AppCell workerName={workerName} slug={cell.slug!} theme={theme} title={cell.title} />
    default:
      return <div className="text-[--text-muted] p-4 text-sm">Unknown: {cell.type}</div>
  }
}

export default function WorkerDashboard() {
  const { name } = useParams<{ name: string }>()
  const [detail, setDetail] = useState<WorkerDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null)

  useEffect(() => {
    if (!name) return
    fetchWorkerDetail(name)
      .then(setDetail)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [name])

  useEffect(() => {
    if (detail) document.body.dataset.theme = detail.theme
    return () => { delete document.body.dataset.theme }
  }, [detail?.theme])

  if (loading) return <div className="p-8 text-[--text-muted]">Loading...</div>
  if (error) return <div className="p-8 text-[--status-error]">{error}</div>
  if (!detail) return null

  const expandedCell = expandedIndex !== null
    ? detail.cells.find(c => c.index === expandedIndex)
    : null

  return (
    <div className="min-h-screen bg-[--bg] p-4">
      <header className="mb-6 flex items-center gap-3">
        <Link to="/"
              className="text-[--text-muted] hover:text-[--text] text-sm min-h-[44px] flex items-center px-1">
          ← Hive
        </Link>
        <h1 className="text-xl font-bold text-[--text]">{detail.name}</h1>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {detail.cells.map(cell => (
          <CellDispatch
            key={cell.index}
            cell={cell}
            workerName={detail.name}
            theme={detail.theme}
            onExpand={() => setExpandedIndex(cell.index)}
          />
        ))}
      </div>

      {expandedCell && (
        <ExpandModal
          isOpen
          title={expandedCell.title}
          onClose={() => setExpandedIndex(null)}
        >
          <CellDispatch
            cell={expandedCell}
            workerName={detail.name}
            theme={detail.theme}
            onExpand={() => {}}
          />
        </ExpandModal>
      )}
    </div>
  )
}
