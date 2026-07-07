import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import TableCell from '../../components/cells/TableCell'

vi.mock('../../hooks/useCellData', () => ({
  useCellData: vi.fn(() => ({
    data: {
      content: [{ name: 'Alice', score: 10 }, { name: 'Bob', score: 5 }],
      title: 'Scores', type: 'table', subtitle: null, is_markdown: false,
    },
    loading: false, error: null, refresh: vi.fn(),
  })),
}))

describe('TableCell', () => {
  it('renders table rows', () => {
    render(<TableCell workerName="w" index={0} title="Scores" onExpand={vi.fn()} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('sorts by column on header click', () => {
    render(<TableCell workerName="w" index={0} title="Scores" onExpand={vi.fn()} />)
    const header = screen.getByText('score')
    fireEvent.click(header)
    const rows = screen.getAllByRole('row')
    // After sort ascending by score: Bob (5) before Alice (10)
    expect(rows[1].textContent).toContain('Bob')
  })
})
