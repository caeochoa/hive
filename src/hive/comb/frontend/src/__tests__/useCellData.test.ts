import { renderHook, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCellData } from '../hooks/useCellData'

vi.mock('../api', () => ({ fetchCell: vi.fn() }))
import { fetchCell } from '../api'

describe('useCellData', () => {
  beforeEach(() => vi.mocked(fetchCell).mockReset())

  it('fetches on mount and returns data', async () => {
    const cellData = { content: '42', title: 'T', type: 'metric' as const, subtitle: null, is_markdown: false }
    vi.mocked(fetchCell).mockResolvedValueOnce(cellData)
    const { result } = renderHook(() => useCellData('budget', 0))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(cellData)
    expect(result.current.error).toBeNull()
  })

  it('sets error on fetch failure', async () => {
    vi.mocked(fetchCell).mockRejectedValueOnce(new Error('network'))
    const { result } = renderHook(() => useCellData('budget', 0))
    await waitFor(() => expect(result.current.error).toBe('network'))
  })

  it('refresh re-fetches', async () => {
    const cellData = { content: '1', title: 'T', type: 'metric' as const, subtitle: null, is_markdown: false }
    vi.mocked(fetchCell).mockResolvedValue(cellData)
    const { result } = renderHook(() => useCellData('budget', 0))
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => result.current.refresh())
    expect(vi.mocked(fetchCell)).toHaveBeenCalledTimes(2)
  })
})
