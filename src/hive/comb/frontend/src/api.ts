import type { WorkerSummary, WorkerDetail, CellData } from './types'

async function _get<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function fetchWorkers(): Promise<WorkerSummary[]> {
  return _get('/api/workers')
}

export function fetchWorkerDetail(name: string): Promise<WorkerDetail> {
  return _get(`/api/workers/${encodeURIComponent(name)}`)
}

export function fetchCell(workerName: string, index: number): Promise<CellData> {
  return _get(`/api/workers/${encodeURIComponent(workerName)}/cells/${index}`)
}

export function openSSEStream(workerName: string, index: number): EventSource {
  return new EventSource(`/api/workers/${encodeURIComponent(workerName)}/cells/${index}/stream`)
}
