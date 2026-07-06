import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import CellCard from '../components/CellCard'

describe('CellCard', () => {
  it('renders title and children', () => {
    render(<CellCard title="My Cell"><span>content</span></CellCard>)
    expect(screen.getByText('My Cell')).toBeInTheDocument()
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  it('calls onRefresh when refresh button clicked', () => {
    const onRefresh = vi.fn()
    render(<CellCard title="T" onRefresh={onRefresh}><span /></CellCard>)
    fireEvent.click(screen.getByTitle('Refresh'))
    expect(onRefresh).toHaveBeenCalledOnce()
  })

  it('calls onExpand when expand button clicked', () => {
    const onExpand = vi.fn()
    render(<CellCard title="T" onExpand={onExpand}><span /></CellCard>)
    fireEvent.click(screen.getByTitle('Expand'))
    expect(onExpand).toHaveBeenCalledOnce()
  })

  it('hides expand button when onExpand not provided', () => {
    render(<CellCard title="T"><span /></CellCard>)
    expect(screen.queryByTitle('Expand')).not.toBeInTheDocument()
  })
})
