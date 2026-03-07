import fs from 'fs'
import path from 'path'
import { strings } from '../i18n/strings'

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
  personalMV:  { fileId: 2, label: strings.categories.personalMV.label,  slug: 'mv' },
  singles:     { fileId: 3, label: strings.categories.singles.label,     slug: 'songs' },
  concerts:    { fileId: 4, label: strings.categories.concerts.label,    slug: 'concerts' },
  variety:     { fileId: 5, label: strings.categories.variety.label,     slug: 'shows' },
  interviews:  { fileId: 6, label: strings.categories.interviews.label,  slug: 'shows' },
  sheMV:       { fileId: 7, label: strings.categories.sheMV.label,      slug: 'mv' },
  collabs:     { fileId: 8, label: strings.categories.collabs.label,    slug: 'songs' },
} as const
