import { useMemo, useState } from 'react'
import CellCard from '../CellCard'
import { useCellData } from '../../hooks/useCellData'

interface Props { workerName: string; index: number; title: string; onExpand: () => void }

export default function TableCell({ workerName, index, title, onExpand }: Props) {
  const { data, loading, error, refresh } = useCellData(workerName, index)
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const rows = (data?.content ?? []) as Record<string, unknown>[]
  const columns = rows.length > 0 ? Object.keys(rows[0]) : []

  const sorted = useMemo(() => {
    if (!sortKey) return rows
    return [...rows].sort((a, b) => {
      const cmp = String(a[sortKey]).localeCompare(String(b[sortKey]), undefined, { numeric: true })
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [rows, sortKey, sortDir])

  const toggleSort = (key: string) => {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  return (
    <CellCard title={title} onRefresh={refresh} onExpand={onExpand}>
      {loading && <div className="text-[--text-muted] text-sm">Loading...</div>}
      {error && <div className="text-[--status-error] text-sm">{error}</div>}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-[--text]">
            <thead>
              <tr>
                {columns.map(col => (
                  <th key={col}
                      className="text-left text-[--text-muted] font-medium py-1 px-2 cursor-pointer hover:text-[--text] select-none"
                      onClick={() => toggleSort(col)}>
                    {col}{sortKey === col ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row, i) => (
                <tr key={i} style={i % 2 === 1 ? { background: 'var(--table-stripe)' } : {}}>
                  {columns.map(col => (
                    <td key={col} className="py-1 px-2">{String(row[col] ?? '')}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </CellCard>
  )
}
