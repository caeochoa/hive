import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import FileCell from '../../components/cells/FileCell'

vi.mock('../../hooks/useCellData', () => ({
  useCellData: vi.fn(() => ({
    data: { content: 'plain text content', title: 'File', type: 'file', subtitle: null, is_markdown: false },
    loading: false, error: null, refresh: vi.fn(),
  })),
}))

describe('FileCell', () => {
  it('renders file content in pre block', () => {
    render(<FileCell workerName="w" index={0} title="File" onExpand={vi.fn()} />)
    expect(screen.getByText('plain text content')).toBeInTheDocument()
  })
})
