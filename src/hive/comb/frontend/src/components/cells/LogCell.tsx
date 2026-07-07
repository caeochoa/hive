import { useEffect, useRef } from 'react'
import CellCard from '../CellCard'
import { useSSELog } from '../../hooks/useSSELog'

interface Props { workerName: string; index: number; title: string; onExpand: () => void }

export default function LogCell({ workerName, index, title, onExpand }: Props) {
  const { lines, reconnect } = useSSELog(workerName, index)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (bottomRef.current?.scrollIntoView) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [lines])

  return (
    <CellCard title={title} onRefresh={reconnect} onExpand={onExpand}>
      <pre className="font-mono text-xs text-[--text] bg-[--pre-bg] overflow-x-auto overflow-y-auto
                      whitespace-pre h-48 p-2 rounded">
        {lines.join('\n')}
        <div ref={bottomRef} />
      </pre>
    </CellCard>
  )
}
