import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import WorkerDashboard from '../pages/WorkerDashboard'

vi.mock('../api', () => ({ fetchWorkerDetail: vi.fn() }))
vi.mock('../hooks/useCellData', () => ({
  useCellData: vi.fn(() => ({
    data: { content: '5', title: 'Count', type: 'metric', subtitle: null, is_markdown: false },
    loading: false, error: null, refresh: vi.fn(),
  })),
}))
vi.mock('../hooks/useSSELog', () => ({
  useSSELog: vi.fn(() => ({ lines: [], reconnect: vi.fn() })),
}))

import { fetchWorkerDetail } from '../api'

function renderWithRoute(name: string) {
  return render(
    <MemoryRouter initialEntries={[`/workers/${name}`]}>
      <Routes>
        <Route path="/workers/:name" element={<WorkerDashboard />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('WorkerDashboard', () => {
  it('renders worker name and cell cards', async () => {
    vi.mocked(fetchWorkerDetail).mockResolvedValueOnce({
      name: 'budget',
      theme: 'terminal-dark',
      cells: [
        { index: 0, type: 'metric', title: 'Tasks', slug: null },
        { index: 1, type: 'log', title: 'Activity', slug: null },
      ],
    })
    renderWithRoute('budget')
    await waitFor(() => expect(screen.getByText('Tasks')).toBeInTheDocument())
    expect(screen.getByText('Activity')).toBeInTheDocument()
  })

  it('shows loading state initially', () => {
    vi.mocked(fetchWorkerDetail).mockReturnValue(new Promise(() => {}))
    renderWithRoute('budget')
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })
})
