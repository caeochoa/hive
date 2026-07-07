import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import MarkdownCell from '../../components/cells/MarkdownCell'

vi.mock('react-markdown', () => ({
  default: ({ children }: { children: string }) => {
    // Simple markdown parsing for testing
    if (children.startsWith('# ')) {
      return <h1>{children.substring(2)}</h1>
    }
    return <p>{children}</p>
  },
}))

describe('MarkdownCell', () => {
  it('renders markdown content as HTML', () => {
    render(<MarkdownCell content="# Hello" />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Hello')
  })

  it('handles empty string without crashing', () => {
    render(<MarkdownCell content="" />)
    expect(screen.getByRole('paragraph')).toBeInTheDocument()
  })
})
