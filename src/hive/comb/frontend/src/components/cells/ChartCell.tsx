import CellCard from '../CellCard'
import { useCellData } from '../../hooks/useCellData'
import type { ChartPoint } from '../../types'

interface Props { workerName: string; index: number; title: string; onExpand: () => void }

export default function ChartCell({ workerName, index, title, onExpand }: Props) {
  const { data, loading, error, refresh } = useCellData(workerName, index)
  const points = (data?.content ?? []) as ChartPoint[]

  const W = 420, H = 120
  const maxVal = points.length > 0 ? Math.max(...points.map(p => p.value), 1) : 1
  const barW = Math.max(4, Math.floor((W - 20) / Math.max(points.length, 1)) - 4)

  return (
    <CellCard title={title} onRefresh={refresh} onExpand={onExpand}>
      {loading && <div className="text-[--text-muted] text-sm">Loading...</div>}
      {error && <div className="text-[--status-error] text-sm">{error}</div>}
      {points.length > 0 && (
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: H }}>
          {points.map((pt, i) => {
            const barH = Math.max(1, Math.round((pt.value / maxVal) * (H - 24)))
            const x = 10 + i * (barW + 4)
            const y = H - 20 - barH
            return (
              <g key={i}>
                <rect x={x} y={y} width={barW} height={barH} fill="var(--accent)" rx={2} />
                <text x={x + barW / 2} y={H - 4} textAnchor="middle"
                      fontSize={10} fill="var(--text-muted)">
                  {pt.label.slice(0, 5)}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </CellCard>
  )
}
