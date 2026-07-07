import CellCard from '../CellCard'
import MarkdownCell from './MarkdownCell'
import { useCellData } from '../../hooks/useCellData'

interface Props { workerName: string; index: number; title: string; onExpand: () => void }

export default function FileCell({ workerName, index, title, onExpand }: Props) {
  const { data, loading, error, refresh } = useCellData(workerName, index)
  return (
    <CellCard title={title} subtitle={data?.subtitle} onRefresh={refresh} onExpand={onExpand}>
      {loading && <div className="text-[--text-muted] text-sm">Loading...</div>}
      {error && <div className="text-[--status-error] text-sm">{error}</div>}
      {data && data.is_markdown
        ? <MarkdownCell content={String(data.content)} />
        : <pre className="font-mono text-xs text-[--text] bg-[--pre-bg] overflow-x-auto whitespace-pre p-2 rounded">
            {String(data?.content ?? '')}
          </pre>
      }
    </CellCard>
  )
}
