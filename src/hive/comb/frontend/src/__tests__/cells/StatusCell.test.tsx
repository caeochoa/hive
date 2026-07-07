import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import StatusCell from '../../components/cells/StatusCell'
import { useCellData } from '../../hooks/useCellData'

vi.mock('../../hooks/useCellData')

const mockUseCellData = useCellData as ReturnType<typeof vi.fn>

describe('StatusCell', () => {
  beforeEach(() => {
    mockUseCellData.mockReturnValue({
      data: { content: { value: 'running', level: 'ok' }, title: 'Health', type: 'status', subtitle: null, is_markdown: false },
      loading: false, error: null, refresh: vi.fn(),
    })
  })

  it('renders status value', () => {
    render(<StatusCell workerName="w" index={0} title="Health" onExpand={vi.fn()} />)
    expect(screen.getByText('running')).toBeInTheDocument()
  })

  it('renders warn status level with warn styling', () => {
    mockUseCellData.mockReturnValue({
      data: { content: { value: 'warning', level: 'warn' }, title: 'Health', type: 'status', subtitle: null, is_markdown: false },
      loading: false, error: null, refresh: vi.fn(),
    })
    render(<StatusCell workerName="w" index={0} title="Health" onExpand={vi.fn()} />)
    expect(screen.getByText('warning')).toBeInTheDocument()
    const statusIndicator = screen.getByText('warning').parentElement?.querySelector('span')
    expect(statusIndicator?.className).toContain('bg-[--status-warn]')
  })

  it('renders error status level gracefully', () => {
    mockUseCellData.mockReturnValue({
      data: { content: { value: 'failed', level: 'error' }, title: 'Health', type: 'status', subtitle: null, is_markdown: false },
      loading: false, error: null, refresh: vi.fn(),
    })
    render(<StatusCell workerName="w" index={0} title="Health" onExpand={vi.fn()} />)
    expect(screen.getByText('failed')).toBeInTheDocument()
    const statusIndicator = screen.getByText('failed').parentElement?.querySelector('span')
    expect(statusIndicator?.className).toContain('bg-[--status-error]')
  })

  it('falls back to neutral styling for unknown status level', () => {
    mockUseCellData.mockReturnValue({
      data: { content: { value: 'unknown', level: 'unknown' }, title: 'Health', type: 'status', subtitle: null, is_markdown: false },
      loading: false, error: null, refresh: vi.fn(),
    })
    render(<StatusCell workerName="w" index={0} title="Health" onExpand={vi.fn()} />)
    expect(screen.getByText('unknown')).toBeInTheDocument()
    const statusIndicator = screen.getByText('unknown').parentElement?.querySelector('span')
    expect(statusIndicator?.className).toContain('bg-[--status-neutral]')
  })
})
