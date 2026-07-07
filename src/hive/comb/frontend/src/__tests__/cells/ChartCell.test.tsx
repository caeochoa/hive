import { render } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ChartCell from '../../components/cells/ChartCell'

vi.mock('../../hooks/useCellData', () => ({
  useCellData: vi.fn(() => ({
    data: {
      content: [{ label: 'Mon', value: 4 }, { label: 'Tue', value: 7 }],
      title: 'Activity', type: 'chart', subtitle: null, is_markdown: false,
    },
    loading: false, error: null, refresh: vi.fn(),
  })),
}))

describe('ChartCell', () => {
  it('renders an SVG chart', () => {
    render(<ChartCell workerName="w" index={0} title="Activity" onExpand={vi.fn()} />)
    expect(document.querySelector('svg')).toBeInTheDocument()
  })
})
