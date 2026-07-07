import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = []
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  closed = false
  constructor(public url: string) { MockEventSource.instances.push(this) }
  close() { this.closed = true }
  emit(data: string) { this.onmessage?.({ data } as MessageEvent) }
}
vi.stubGlobal('EventSource', MockEventSource)

import { useSSELog } from '../hooks/useSSELog'

describe('useSSELog', () => {
  beforeEach(() => { MockEventSource.instances = [] })

  it('opens EventSource at correct URL', () => {
    renderHook(() => useSSELog('budget', 3))
    expect(MockEventSource.instances[0].url).toBe('/api/workers/budget/cells/3/stream')
  })

  it('appends lines on message', () => {
    const { result } = renderHook(() => useSSELog('budget', 0))
    act(() => MockEventSource.instances[0].emit('log line 1'))
    act(() => MockEventSource.instances[0].emit('log line 2'))
    expect(result.current.lines).toEqual(['log line 1', 'log line 2'])
  })

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() => useSSELog('budget', 0))
    const src = MockEventSource.instances[0]
    unmount()
    expect(src.closed).toBe(true)
  })
})
