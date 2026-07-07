import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import TableCell from '../../components/cells/TableCell'
import { useCellData } from '../../hooks/useCellData'

vi.mock('../../hooks/useCellData')

const mockUseCellData = vi.mocked(useCellData)

describe('TableCell', () => {
  beforeEach(() => {
    mockUseCellData.mockReturnValue({
      data: {
        content: [{ name: 'Alice', score: 10 }, { name: 'Bob', score: 5 }],
        title: 'Scores', type: 'table', subtitle: null, is_markdown: false,
      },
      loading: false, error: null, refresh: vi.fn(),
    })
  })

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

  it('renders loading state', () => {
    mockUseCellData.mockReturnValueOnce({
      data: null,
      loading: true,
      error: null,
      refresh: vi.fn(),
    } as any)
    render(<TableCell workerName="w" index={0} title="Scores" onExpand={vi.fn()} />)
    expect(screen.getByText(/loading|Loading/i)).toBeInTheDocument()
  })
})
