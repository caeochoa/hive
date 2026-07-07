import { render, screen, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../api', () => ({
  fetchWorkers: vi.fn(),
}))

import WorkerList from '../pages/WorkerList'
import { fetchWorkers } from '../api'

describe('WorkerList', () => {
  beforeEach(() => vi.mocked(fetchWorkers).mockReset())

  it('renders a card for each worker', async () => {
    vi.mocked(fetchWorkers).mockResolvedValueOnce([
      { name: 'budget', theme: 'terminal-dark', cell_count: 3 },
      { name: 'news', theme: 'clean-light', cell_count: 1 },
    ])
    render(<MemoryRouter><WorkerList /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('budget')).toBeInTheDocument())
    expect(screen.getByText('news')).toBeInTheDocument()
    expect(screen.getByText('3 cells')).toBeInTheDocument()
  })

  it('shows loading state initially', async () => {
    let resolve: (v: never[]) => void
    const deferred = new Promise<never[]>(res => { resolve = res })
    vi.mocked(fetchWorkers).mockReturnValueOnce(deferred)
    render(<MemoryRouter><WorkerList /></MemoryRouter>)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
    // Resolve the promise so no pending microtasks leak into subsequent tests
    await act(async () => { resolve!([]) })
  })

  it('shows error when fetch fails', async () => {
    vi.mocked(fetchWorkers).mockRejectedValueOnce(new Error('Network error'))
    render(<MemoryRouter><WorkerList /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/network error/i)).toBeInTheDocument(), { timeout: 1000 })
  })
})
