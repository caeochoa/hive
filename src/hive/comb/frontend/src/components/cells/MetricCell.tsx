import CellCard from '../CellCard'
import { useCellData } from '../../hooks/useCellData'

interface Props { workerName: string; index: number; title: string; onExpand: () => void }

export default function MetricCell({ workerName, index, title, onExpand }: Props) {
  const { data, loading, error, refresh } = useCellData(workerName, index)
  return (
    <CellCard title={title} onRefresh={refresh} onExpand={onExpand}>
      {loading && <div className="text-[--text-muted] text-sm">Loading...</div>}
      {error && <div className="text-[--status-error] text-sm">{error}</div>}
      {data && (
        <div className="text-5xl font-bold text-[--metric-color] py-2">
          {String(data.content)}
        </div>
      )}
    </CellCard>
  )
}
