import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchCell } from '../api'
import type { CellData } from '../types'

const POLL_INTERVAL = 10_000

export function useCellData(workerName: string, index: number) {
  const [data, setData] = useState<CellData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval>>()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchCell(workerName, index))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [workerName, index])

  useEffect(() => {
    load()
    timerRef.current = setInterval(load, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [load])

  return { data, loading, error, refresh: load }
}
