import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import LogCell from '../../components/cells/LogCell'
import { useSSELog } from '../../hooks/useSSELog'

vi.mock('../../hooks/useSSELog')

const mockUseSSELog = vi.mocked(useSSELog)

describe('LogCell', () => {
  beforeEach(() => {
    mockUseSSELog.mockReturnValue({ lines: ['line one', 'line two'], reconnect: vi.fn() })
  })

  it('renders log lines', () => {
    render(<LogCell workerName="w" index={0} title="Logs" onExpand={vi.fn()} />)
    expect(screen.getByText(/line one/)).toBeInTheDocument()
  })

  it('renders lines from hook', () => {
    render(<LogCell workerName="w" index={0} title="Logs" onExpand={vi.fn()} />)
    expect(screen.getByText(/line two/)).toBeInTheDocument()
  })

  it('calls reconnect on refresh', () => {
    const reconnectMock = vi.fn()
    mockUseSSELog.mockReturnValueOnce({
      lines: ['line one'],
      reconnect: reconnectMock,
    })
    const { container } = render(<LogCell workerName="w" index={0} title="Logs" onExpand={vi.fn()} />)
    const refreshButton = container.querySelector('[title="Refresh"]') as HTMLButtonElement
    fireEvent.click(refreshButton!)
    expect(reconnectMock).toHaveBeenCalled()
  })
})
