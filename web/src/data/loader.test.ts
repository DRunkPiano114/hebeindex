import { describe, it, expect } from 'vitest'
import { deriveSlug, loadAllArtists, loadCategory } from './loader'

describe('deriveSlug', () => {
  it('converts spaces to underscores and lowercases', () => {
    expect(deriveSlug('Hebe Tien')).toBe('hebe_tien')
  })

  it('removes dots', () => {
    expect(deriveSlug('G.E.M.')).toBe('gem')
  })

  it('handles simple two-word names', () => {
    expect(deriveSlug('Jay Chou')).toBe('jay_chou')
  })

  it('handles multi-word names', () => {
    expect(deriveSlug('David Tao')).toBe('david_tao')
  })

  it('preserves hyphens', () => {
    expect(deriveSlug('A-Lin')).toBe('a-lin')
  })
})

describe('loadAllArtists', () => {
  it('returns an array', () => {
    const artists = loadAllArtists()
    expect(Array.isArray(artists)).toBe(true)
  })

  it('only includes artists with processed data', () => {
    const artists = loadAllArtists()
    // Only hebe_tien has data currently
    for (const artist of artists) {
      expect(artist.slug).toBeTruthy()
      expect(artist.categories.length).toBeGreaterThan(0)
    }
  })

  it('parses category metadata from YAML', () => {
    const artists = loadAllArtists()
    if (artists.length === 0) return // skip if no data
    const first = artists[0]
    for (const cat of first.categories) {
      expect(cat.id).toBeTypeOf('number')
      expect(cat.key).toBeTypeOf('string')
      expect(cat.label).toBeTypeOf('string')
      expect(cat.sub).toBeTypeOf('string')
    }
  })

  it('includes artist names', () => {
    const artists = loadAllArtists()
    if (artists.length === 0) return
    const first = artists[0]
    expect(first.names.primary).toBeTruthy()
    expect(first.names.english).toBeTruthy()
  })
})

describe('loadCategory', () => {
  it('loads data for a valid artist and file ID', () => {
    const artists = loadAllArtists()
    if (artists.length === 0) return
    const artist = artists[0]
    const cat = artist.categories[0]
    const items = loadCategory(artist.slug, cat.id)
    expect(Array.isArray(items)).toBe(true)
  })

  it('returns empty array for non-existent file', () => {
    const items = loadCategory('nonexistent_artist', 999)
    expect(items).toEqual([])
  })
})
