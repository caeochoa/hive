import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ChartCell from '../../components/cells/ChartCell'
import { useCellData } from '../../hooks/useCellData'

vi.mock('../../hooks/useCellData')

const mockUseCellData = vi.mocked(useCellData)

describe('ChartCell', () => {
  beforeEach(() => {
    mockUseCellData.mockReturnValue({
      data: {
        content: [{ label: 'Mon', value: 4 }, { label: 'Tue', value: 7 }],
        title: 'Activity', type: 'chart', subtitle: null, is_markdown: false,
      },
      loading: false, error: null, refresh: vi.fn(),
    })
  })

  it('renders an SVG chart', () => {
    render(<ChartCell workerName="w" index={0} title="Activity" onExpand={vi.fn()} />)
    expect(document.querySelector('svg')).toBeInTheDocument()
  })

  it('renders loading state', () => {
    mockUseCellData.mockReturnValueOnce({
      data: null,
      loading: true,
      error: null,
      refresh: vi.fn(),
    } as any)
    render(<ChartCell workerName="w" index={0} title="Activity" onExpand={vi.fn()} />)
    expect(screen.getByText(/loading|Loading/i)).toBeInTheDocument()
  })

  it('renders error state', () => {
    mockUseCellData.mockReturnValueOnce({
      data: null,
      loading: false,
      error: 'Failed to load chart',
      refresh: vi.fn(),
    } as any)
    render(<ChartCell workerName="w" index={0} title="Activity" onExpand={vi.fn()} />)
    expect(screen.getByText(/error|failed/i)).toBeInTheDocument()
  })
})
