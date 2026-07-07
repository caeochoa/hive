import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import MetricCell from '../../components/cells/MetricCell'

vi.mock('../../hooks/useCellData', () => ({
  useCellData: vi.fn(() => ({
    data: { content: '99', title: 'Score', type: 'metric', subtitle: null, is_markdown: false },
    loading: false, error: null, refresh: vi.fn(),
  })),
}))

describe('MetricCell', () => {
  it('renders metric value prominently', () => {
    render(<MetricCell workerName="w" index={0} title="Score" onExpand={vi.fn()} />)
    expect(screen.getByText('99')).toBeInTheDocument()
    expect(screen.getByText('Score')).toBeInTheDocument()
  })
})
