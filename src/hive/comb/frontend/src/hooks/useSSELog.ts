import { useEffect, useRef, useState } from 'react'
import { openSSEStream } from '../api'

export function useSSELog(workerName: string, index: number) {
  const [lines, setLines] = useState<string[]>([])
  const sourceRef = useRef<EventSource | null>(null)

  const connect = () => {
    sourceRef.current?.close()
    setLines([])
    const src = openSSEStream(workerName, index)
    src.onmessage = (e: MessageEvent) => setLines(prev => [...prev, e.data])
    src.onerror = () => {
      sourceRef.current?.close()
      setTimeout(connect, 3000)
    }
    sourceRef.current = src
  }

  useEffect(() => {
    connect()
    return () => sourceRef.current?.close()
  }, [workerName, index]) // eslint-disable-line react-hooks/exhaustive-deps

  return { lines, reconnect: connect }
}
