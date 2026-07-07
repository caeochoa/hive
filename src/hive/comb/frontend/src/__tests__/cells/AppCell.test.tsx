import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import AppCell from '../../components/cells/AppCell'

describe('AppCell', () => {
  it('renders an iframe with correct src', () => {
    render(<AppCell workerName="budget" slug="my-app" theme="terminal-dark" title="My App" />)
    const iframe = document.querySelector('iframe')
    expect(iframe).toBeInTheDocument()
    expect(iframe?.src).toContain('/workers/budget/apps/my-app')
    expect(iframe?.src).toContain('theme=terminal-dark')
  })

  it('renders title', () => {
    render(<AppCell workerName="budget" slug="my-app" theme="terminal-dark" title="My App" />)
    expect(screen.getByText('My App')).toBeInTheDocument()
  })
})
