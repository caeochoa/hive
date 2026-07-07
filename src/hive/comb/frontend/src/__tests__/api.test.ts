import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchWorkers, fetchWorkerDetail, fetchCell } from '../api'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

beforeEach(() => mockFetch.mockReset())

describe('fetchWorkers', () => {
  it('calls /api/workers and returns parsed json', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [{ name: 'budget', theme: 'terminal-dark', cell_count: 2 }],
    })
    const result = await fetchWorkers()
    expect(mockFetch).toHaveBeenCalledWith('/api/workers')
    expect(result[0].name).toBe('budget')
  })

  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })
    await expect(fetchWorkers()).rejects.toThrow('HTTP 500')
  })
})

describe('fetchWorkerDetail', () => {
  it('encodes worker name in URL', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ name: 'my worker', theme: 'clean-light', cells: [] }),
    })
    await fetchWorkerDetail('my worker')
    expect(mockFetch).toHaveBeenCalledWith('/api/workers/my%20worker')
  })
})

describe('fetchCell', () => {
  it('calls correct URL', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ content: '42', title: 'Tasks', type: 'metric', subtitle: null, is_markdown: false }),
    })
    await fetchCell('budget', 0)
    expect(mockFetch).toHaveBeenCalledWith('/api/workers/budget/cells/0')
  })
})
