import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import MetricCell from '../../components/cells/MetricCell'
import { useCellData } from '../../hooks/useCellData'

vi.mock('../../hooks/useCellData')

const mockUseCellData = useCellData as ReturnType<typeof vi.fn>

describe('MetricCell', () => {
  beforeEach(() => {
    mockUseCellData.mockReturnValue({
      data: { content: '99', title: 'Score', type: 'metric', subtitle: null, is_markdown: false },
      loading: false, error: null, refresh: vi.fn(),
    })
  })

  it('renders metric value prominently', () => {
    render(<MetricCell workerName="w" index={0} title="Score" onExpand={vi.fn()} />)
    expect(screen.getByText('99')).toBeInTheDocument()
    expect(screen.getByText('Score')).toBeInTheDocument()
  })

  it('renders loading state when data is loading', () => {
    mockUseCellData.mockReturnValue({
      data: null,
      loading: true,
      error: null,
      refresh: vi.fn(),
    })
    render(<MetricCell workerName="w" index={0} title="Score" onExpand={vi.fn()} />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('renders error state when fetch fails', () => {
    mockUseCellData.mockReturnValue({
      data: null,
      loading: false,
      error: 'fetch failed',
      refresh: vi.fn(),
    })
    render(<MetricCell workerName="w" index={0} title="Score" onExpand={vi.fn()} />)
    expect(screen.getByText('fetch failed')).toBeInTheDocument()
  })
})
