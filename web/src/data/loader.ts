import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'

const COLLECTOR_DIR = path.resolve(process.cwd(), '../collector')
const ARTISTS_DIR = path.join(COLLECTOR_DIR, 'artists')
const DATA_DIR = path.join(COLLECTOR_DIR, 'data')

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

export interface CategoryMeta {
  id: number
  key: string
  label: string
  sub: string
}

export interface ArtistMeta {
  slug: string
  names: { primary: string; english: string }
  birthYear?: number
  genre?: string
  awards: string[]
  group?: { name: string }
  categories: CategoryMeta[]
}

/**
 * Derive URL-safe slug from english name.
 * Must match collector/artist_profile.py:slug()
 */
export function deriveSlug(englishName: string): string {
  return englishName.toLowerCase().replaceAll(' ', '_').replaceAll('.', '')
}

/**
 * Discover all artists that have both a YAML profile and processed data.
 */
export function loadAllArtists(): ArtistMeta[] {
  if (!fs.existsSync(ARTISTS_DIR)) return []

  const yamlFiles = fs.readdirSync(ARTISTS_DIR).filter(f => f.endsWith('.yaml')).sort()
  const artists: ArtistMeta[] = []

  for (const file of yamlFiles) {
    try {
      const raw = yaml.load(
        fs.readFileSync(path.join(ARTISTS_DIR, file), 'utf-8')
      ) as Record<string, any>

      const artist = raw.artist
      if (!artist?.names?.english) continue

      const slug = deriveSlug(artist.names.english)
      const processedDir = path.join(DATA_DIR, slug, 'processed')

      // Only include artists that have processed data
      if (!fs.existsSync(processedDir)) continue

      const categories: CategoryMeta[] = (raw.categories || []).map((c: any) => ({
        id: c.id,
        key: c.key,
        label: c.label,
        sub: c.sub || '',
      }))

      artists.push({
        slug,
        names: { primary: artist.names.primary, english: artist.names.english },
        birthYear: artist.birth_year,
        genre: artist.genre,
        awards: artist.awards || [],
        group: raw.group ? { name: raw.group.name } : undefined,
        categories,
      })
    } catch (err) {
      console.error(`Failed to parse artist YAML: ${file}`, err)
    }
  }

  return artists
}

/**
 * Load video data for a specific artist category.
 */
export function loadCategory(slug: string, fileId: number): ContentItem[] {
  const filePath = path.join(DATA_DIR, slug, 'processed', `file_${fileId}.json`)

  if (!fs.existsSync(filePath)) {
    console.warn(`No data file: ${filePath}`)
    return []
  }

  const raw = JSON.parse(fs.readFileSync(filePath, 'utf-8'))
  return (raw.results ?? []) as ContentItem[]
}
