import { useEffect, useRef, useState } from 'react'
import { openSSEStream } from '../api'

export function useSSELog(workerName: string, index: number) {
  const [lines, setLines] = useState<string[]>([])
  const sourceRef = useRef<EventSource | null>(null)
  const retryCountRef = useRef(0)
  const MAX_RETRIES = 5
  const RETRY_DELAY_MS = 3000

  const connect = () => {
    sourceRef.current?.close()
    setLines([])
    const src = openSSEStream(workerName, index)
    src.onmessage = (e: MessageEvent) => {
      setLines(prev => [...prev, e.data])
      // Reset retry count on successful message
      retryCountRef.current = 0
    }
    src.onerror = () => {
      sourceRef.current?.close()
      if (retryCountRef.current < MAX_RETRIES) {
        retryCountRef.current += 1
        setTimeout(connect, RETRY_DELAY_MS)
      }
    }
    sourceRef.current = src
  }

  useEffect(() => {
    retryCountRef.current = 0
    connect()
    return () => sourceRef.current?.close()
  }, [workerName, index]) // eslint-disable-line react-hooks/exhaustive-deps -- connect is stable via ref

  return { lines, reconnect: connect }
}
