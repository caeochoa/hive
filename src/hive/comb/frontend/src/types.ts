export type CellType = 'log' | 'file' | 'markdown' | 'metric' | 'status' | 'table' | 'chart' | 'app'
export type ThemeName = 'terminal-dark' | 'clean-light' | 'bold-dark'

export interface WorkerSummary {
  name: string
  theme: ThemeName
  cell_count: number
}

export interface CellMeta {
  index: number
  type: CellType
  title: string
  slug: string | null
}

export interface WorkerDetail {
  name: string
  theme: ThemeName
  cells: CellMeta[]
}

export interface StatusContent {
  value: string
  level: 'ok' | 'warn' | 'error' | 'neutral'
}

export interface ChartPoint {
  label: string
  value: number
}

export interface CellData {
  content: unknown
  title: string
  type: CellType
  subtitle: string | null
  is_markdown: boolean
}
