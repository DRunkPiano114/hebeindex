import fs from 'fs'
import path from 'path'

const PROCESSED_DIR = path.resolve(process.cwd(), '../collector/processed')

export interface ContentItem {
  title: string
  url: string
  source: 'youtube' | 'bilibili' | 'google'
  published_at?: string
  view_count?: number
  play_count?: number
  channel?: string
  author?: string
  duration?: string
  verified: boolean
  verify_status?: number
  search_query?: string
  bvid?: string
  description?: string
}

export function loadCategory(fileId: number): ContentItem[] {
  const raw = JSON.parse(fs.readFileSync(path.join(PROCESSED_DIR, `file_${fileId}.json`), 'utf-8'))
  return raw.results as ContentItem[]
}

export const CATEGORIES = {
  personalMV:  { fileId: 2, label: '个人 MV',   slug: 'mv' },
  singles:     { fileId: 3, label: '影视单曲',   slug: 'songs' },
  concerts:    { fileId: 4, label: '演唱会',     slug: 'concerts' },
  variety:     { fileId: 5, label: '综艺节目',   slug: 'shows' },
  interviews:  { fileId: 6, label: '采访访谈',   slug: 'shows' },
  sheMV:       { fileId: 7, label: 'S.H.E MV',  slug: 'mv' },
  collabs:     { fileId: 8, label: '合唱合作',   slug: 'songs' },
} as const
