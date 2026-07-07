import { useEffect, useState } from 'react'
import { THEME_ACCENT } from '../../themes'
import type { ThemeName } from '../../types'

interface Props { workerName: string; slug: string; theme: ThemeName; title: string }

export default function AppCell({ workerName, slug, theme, title }: Props) {
  const [height, setHeight] = useState(400)
  const accent = encodeURIComponent(THEME_ACCENT[theme] ?? '#58a6ff')
  const src = `/workers/${encodeURIComponent(workerName)}/apps/${slug}?theme=${theme}&accent=${accent}`

  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.data?.type === 'hive:resize' && typeof e.data.height === 'number') {
        setHeight(e.data.height)
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  return (
    <div className="flex flex-col rounded-[10px] border border-[--border] bg-[--surface]">
      <div className="flex items-center justify-between border-b border-[--border] bg-[--header-bg] px-3.5 min-h-[44px]">
        <div className="text-[0.75rem] font-semibold uppercase tracking-wide text-[--text-muted]">
          {title}
        </div>
        <a href={src} target="_blank" rel="noreferrer"
           className="text-xs text-[--text-muted] hover:text-[--text] px-2 py-2 min-h-[44px] flex items-center"
           title="Open in new tab">
          ↗
        </a>
      </div>
      <iframe src={src} title={title}
              style={{ height, border: 'none', width: '100%' }}
              sandbox="allow-scripts allow-same-origin allow-forms" />
    </div>
  )
}
