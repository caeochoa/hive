import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import LogCell from '../../components/cells/LogCell'

vi.mock('../../hooks/useSSELog', () => ({
  useSSELog: vi.fn(() => ({ lines: ['line one', 'line two'], reconnect: vi.fn() })),
}))

describe('LogCell', () => {
  it('renders log lines', () => {
    render(<LogCell workerName="w" index={0} title="Logs" onExpand={vi.fn()} />)
    expect(screen.getByText(/line one/)).toBeInTheDocument()
  })
})
