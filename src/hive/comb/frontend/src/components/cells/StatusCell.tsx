import CellCard from '../CellCard'
import { useCellData } from '../../hooks/useCellData'
import type { StatusContent } from '../../types'

interface Props { workerName: string; index: number; title: string; onExpand: () => void }

const LEVEL_CLASS: Record<string, string> = {
  ok: 'bg-[--status-ok]',
  warn: 'bg-[--status-warn]',
  error: 'bg-[--status-error]',
  neutral: 'bg-[--status-neutral]',
}

export default function StatusCell({ workerName, index, title, onExpand }: Props) {
  const { data, loading, error, refresh } = useCellData(workerName, index)
  const status = data?.content as StatusContent | undefined
  return (
    <CellCard title={title} onRefresh={refresh} onExpand={onExpand}>
      {loading && <div className="text-[--text-muted] text-sm">Loading...</div>}
      {error && <div className="text-[--status-error] text-sm">{error}</div>}
      {status && (
        <div className="flex items-center gap-2 py-1">
          <span className={`inline-block w-2.5 h-2.5 rounded-full ${LEVEL_CLASS[status.level] ?? LEVEL_CLASS.neutral}`} />
          <span className="text-[--text] font-medium">{status.value}</span>
        </div>
      )}
    </CellCard>
  )
}
