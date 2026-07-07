import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import StatusCell from '../../components/cells/StatusCell'

vi.mock('../../hooks/useCellData', () => ({
  useCellData: vi.fn(() => ({
    data: { content: { value: 'running', level: 'ok' }, title: 'Health', type: 'status', subtitle: null, is_markdown: false },
    loading: false, error: null, refresh: vi.fn(),
  })),
}))

describe('StatusCell', () => {
  it('renders status value', () => {
    render(<StatusCell workerName="w" index={0} title="Health" onExpand={vi.fn()} />)
    expect(screen.getByText('running')).toBeInTheDocument()
  })
})
