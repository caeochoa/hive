import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import FileCell from '../../components/cells/FileCell'
import { useCellData } from '../../hooks/useCellData'

vi.mock('../../hooks/useCellData')
vi.mock('../../components/cells/MarkdownCell', () => ({
  default: ({ content }: { content: string }) => <div data-testid="markdown-cell">{content}</div>,
}))

const mockUseCellData = useCellData as ReturnType<typeof vi.fn>

describe('FileCell', () => {
  beforeEach(() => {
    mockUseCellData.mockReturnValue({
      data: { content: 'plain text content', title: 'File', type: 'file', subtitle: null, is_markdown: false },
      loading: false, error: null, refresh: vi.fn(),
    })
  })

  it('renders file content in pre block', () => {
    render(<FileCell workerName="w" index={0} title="File" onExpand={vi.fn()} />)
    expect(screen.getByText('plain text content')).toBeInTheDocument()
  })

  it('renders markdown content via MarkdownCell when is_markdown is true', () => {
    mockUseCellData.mockReturnValue({
      data: { content: '# Hello\n\nMarkdown content', title: 'File', type: 'file', subtitle: null, is_markdown: true },
      loading: false, error: null, refresh: vi.fn(),
    })
    render(<FileCell workerName="w" index={0} title="File" onExpand={vi.fn()} />)
    expect(screen.getByTestId('markdown-cell')).toBeInTheDocument()
    // Verify markdown cell received the content
    const markdownCell = screen.getByTestId('markdown-cell')
    expect(markdownCell.textContent).toContain('# Hello')
  })

  it('displays subtitle when provided', () => {
    mockUseCellData.mockReturnValue({
      data: { content: 'file content', title: 'File', type: 'file', subtitle: 'file.md', is_markdown: false },
      loading: false, error: null, refresh: vi.fn(),
    })
    render(<FileCell workerName="w" index={0} title="File" onExpand={vi.fn()} />)
    expect(screen.getByText('file.md')).toBeInTheDocument()
  })
})
