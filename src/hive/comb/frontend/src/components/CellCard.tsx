interface CellCardProps {
  title: string
  subtitle?: string | null
  onRefresh?: () => void
  onExpand?: () => void
  children: React.ReactNode
}

export default function CellCard({ title, subtitle, onRefresh, onExpand, children }: CellCardProps) {
  return (
    <div className="flex flex-col overflow-hidden rounded-[10px] border border-[--border] bg-[--surface]"
         style={{ boxShadow: 'var(--shadow)' }}>
      <div className="flex items-center justify-between border-b border-[--border] bg-[--header-bg] px-3.5 min-h-[44px]">
        <div>
          <div className="text-[0.75rem] font-semibold uppercase tracking-wide text-[--text-muted]">
            {title}
          </div>
          {subtitle && (
            <div className="text-[0.7rem] text-[--text-muted] mt-0.5">{subtitle}</div>
          )}
        </div>
        <div className="flex gap-1">
          {onRefresh && (
            <button title="Refresh" onClick={onRefresh}
                    className="rounded px-2 py-2 text-[--text-muted] text-sm hover:bg-[--btn-hover] hover:text-[--text] min-h-[44px]">
              ↺
            </button>
          )}
          {onExpand && (
            <button title="Expand" onClick={onExpand}
                    className="rounded px-2 py-2 text-[--text-muted] text-sm hover:bg-[--btn-hover] hover:text-[--text] min-h-[44px]">
              ⤢
            </button>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-hidden p-3.5">
        {children}
      </div>
    </div>
  )
}
