import { useEffect } from 'react'
import { createPortal } from 'react-dom'

interface ExpandModalProps {
  isOpen: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
}

export default function ExpandModal({ isOpen, title, onClose, children }: ExpandModalProps) {
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-6"
         style={{ backgroundColor: 'var(--modal-overlay)' }}
         onClick={onClose}>
      <div className="relative w-full h-[85dvh] sm:h-auto sm:max-w-4xl sm:max-h-[85vh]
                      bg-[--surface] sm:rounded-xl overflow-hidden flex flex-col"
           onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-[--border] px-4 min-h-[44px]">
          <span className="font-semibold text-[--text]">{title}</span>
          <button onClick={onClose}
                  className="text-[--text-muted] hover:text-[--text] text-xl px-3 py-2 min-h-[44px]">
            ×
          </button>
        </div>
        <div className="flex-1 overflow-auto p-4">{children}</div>
      </div>
    </div>,
    document.body
  )
}
