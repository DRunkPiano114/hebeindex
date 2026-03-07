import { useRef, useState, useMemo, useCallback } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import Fuse from 'fuse.js'
import { strings } from '../i18n/strings'

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
}

type SortKey = 'date' | 'plays'
type SortDir = 'desc' | 'asc'
type Platform = 'all' | 'youtube' | 'bilibili'

function formatCount(n?: number): string {
  if (!n) return '—'
  if (n >= 100_000_000) return (n / 100_000_000).toFixed(1) + strings.yi
  if (n >= 10_000_000) return (n / 10_000_000).toFixed(0) + strings.qianwan
  if (n >= 10_000) return (n / 10_000).toFixed(0) + strings.wan
  return n.toLocaleString()
}

function formatDate(s?: string): string {
  if (!s) return '—'
  return s.slice(0, 7) // YYYY-MM
}

function PlatformBadge({ source }: { source: string }) {
  if (source === 'youtube') {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24 }}>
        <svg width="20" height="14" viewBox="0 0 20 14" fill="none">
          <rect width="20" height="14" rx="3" fill="#FF0000" />
          <path d="M8 4v6l5-3-5-3z" fill="#fff" />
        </svg>
      </span>
    )
  }
  if (source === 'bilibili') {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24 }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path d="M6.15 4.56a.7.7 0 0 1 .98-.14l2.87 2.1h4l2.87-2.1a.7.7 0 0 1 .84 1.12L16.2 6.52h1.3A3.5 3.5 0 0 1 21 10.02v5.5a3.5 3.5 0 0 1-3.5 3.5h-11A3.5 3.5 0 0 1 3 15.52v-5.5a3.5 3.5 0 0 1 3.5-3.5h1.3L6.29 5.54a.7.7 0 0 1-.14-.98zM6.5 8.02a2 2 0 0 0-2 2v5.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-5.5a2 2 0 0 0-2-2h-11z" fill="#00A1D6"/>
          <path d="M8.5 11.52a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1zM15.5 11.52a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1z" fill="#00A1D6"/>
        </svg>
      </span>
    )
  }
  return (
    <span style={{
      display: 'inline-block', padding: '1px 6px', borderRadius: 3,
      backgroundColor: '#F5F5F4', color: '#78716C',
      fontSize: 11, fontWeight: 500,
    }}>WEB</span>
  )
}

interface Props {
  items: ContentItem[]
  searchPlaceholder?: string
}

export default function ContentTable({ items, searchPlaceholder = strings.searchPlaceholder }: Props) {
  const [query, setQuery] = useState('')
  const [platform, setPlatform] = useState<Platform>('all')
  const [sort, setSort] = useState<SortKey>('plays')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const toggleSort = (key: SortKey) => {
    if (sort === key) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSort(key)
      setSortDir('desc')
    }
  }
  const parentRef = useRef<HTMLDivElement>(null)

  const fuse = useMemo(() => new Fuse(items, {
    keys: ['title'],
    threshold: 0.35,
    minMatchCharLength: 1,
  }), [items])

  const filtered = useMemo(() => {
    let result = query.trim()
      ? fuse.search(query).map(r => r.item)
      : [...items]

    if (platform !== 'all') {
      result = result.filter(i => i.source === platform)
    }

    const dir = sortDir === 'desc' ? 1 : -1
    result.sort((a, b) => {
      if (sort === 'date') {
        return dir * (b.published_at ?? '').localeCompare(a.published_at ?? '')
      }
      const pa = (a.view_count ?? a.play_count ?? 0)
      const pb = (b.view_count ?? b.play_count ?? 0)
      return dir * (pb - pa)
    })

    return result
  }, [query, platform, sort, sortDir, fuse, items])

  const rowVirtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 44,
    overscan: 10,
  })

  const ytCount = useMemo(() => items.filter(i => i.source === 'youtube').length, [items])
  const blCount = useMemo(() => items.filter(i => i.source === 'bilibili').length, [items])

  const handleRowClick = useCallback((url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer')
  }, [])

  const btnStyle = (active: boolean) => ({
    display: 'inline-flex' as const,
    alignItems: 'center' as const,
    gap: 4,
    padding: '6px 12px',
    borderRadius: 4,
    border: '1px solid',
    borderColor: active ? 'var(--accent)' : 'var(--divider)',
    backgroundColor: active ? 'var(--accent)' : 'transparent',
    color: active ? '#fff' : 'var(--text-secondary)',
    fontSize: 12,
    lineHeight: 1,
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', flex: 1 }}>
      {/* Controls */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 16 }}>
        <input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder={searchPlaceholder}
          style={{
            flex: '1 1 200px', minWidth: 160,
            padding: '6px 12px',
            border: '1px solid var(--divider)',
            borderRadius: 4,
            backgroundColor: 'transparent',
            color: 'var(--text-primary)',
            fontSize: 13,
            outline: 'none',
          }}
        />
        <div style={{ display: 'flex', gap: 6 }}>
          {(['all', 'youtube', 'bilibili'] as Platform[]).map(p => (
            <button key={p} style={btnStyle(platform === p)} onClick={() => setPlatform(p)}>
              {p === 'all' ? `${strings.filterAll} ${items.length}` : p === 'youtube' ? (<><svg width="16" height="11" viewBox="0 0 20 14" fill="none" style={{ display: 'block', flexShrink: 0 }}><rect width="20" height="14" rx="3" fill={platform === 'youtube' ? '#fff' : '#FF0000'} /><path d="M8 4v6l5-3-5-3z" fill={platform === 'youtube' ? '#FF0000' : '#fff'} /></svg>{ytCount}</>) : (<><svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ display: 'block', flexShrink: 0 }}><path d="M6.15 4.56a.7.7 0 0 1 .98-.14l2.87 2.1h4l2.87-2.1a.7.7 0 0 1 .84 1.12L16.2 6.52h1.3A3.5 3.5 0 0 1 21 10.02v5.5a3.5 3.5 0 0 1-3.5 3.5h-11A3.5 3.5 0 0 1 3 15.52v-5.5a3.5 3.5 0 0 1 3.5-3.5h1.3L6.29 5.54a.7.7 0 0 1-.14-.98zM6.5 8.02a2 2 0 0 0-2 2v5.5a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-5.5a2 2 0 0 0-2-2h-11z" fill={platform === 'bilibili' ? '#fff' : '#00A1D6'}/><path d="M8.5 11.52a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1zM15.5 11.52a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1z" fill={platform === 'bilibili' ? '#fff' : '#00A1D6'}/></svg>{blCount}</>)}
            </button>
          ))}
        </div>
      </div>

      {/* Count */}
      <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginBottom: 8 }}>
        {strings.showCount(filtered.length, items.length)}
      </div>

      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '52px 1fr 90px 100px',
        padding: '8px 20px 8px 12px',
        borderBottom: '1px solid var(--divider)',
        borderTop: '1px solid var(--divider)',
        color: 'var(--text-secondary)',
        fontSize: 12,
        fontWeight: 500,
        letterSpacing: '0.03em',
      }}>
        <span>{strings.tableHeaderPlatform}</span>
        <span>{strings.tableHeaderTitle}</span>
        <span
          onClick={() => toggleSort('date')}
          style={{
            textAlign: 'right', cursor: 'pointer', userSelect: 'none',
            color: sort === 'date' ? 'var(--accent)' : 'var(--text-secondary)',
            fontWeight: sort === 'date' ? 600 : 500,
          }}
        >
          {strings.tableHeaderDate}<span style={{ display: 'inline-block', width: 14, textAlign: 'center' }}>{sort === 'date' ? (sortDir === 'desc' ? '↓' : '↑') : '↕'}</span>
        </span>
        <span
          onClick={() => toggleSort('plays')}
          style={{
            textAlign: 'right', cursor: 'pointer', userSelect: 'none',
            color: sort === 'plays' ? 'var(--accent)' : 'var(--text-secondary)',
            fontWeight: sort === 'plays' ? 600 : 500,
          }}
        >
          {strings.tableHeaderPlays}<span style={{ display: 'inline-block', width: 14, textAlign: 'center' }}>{sort === 'plays' ? (sortDir === 'desc' ? '↓' : '↑') : '↕'}</span>
        </span>
      </div>

      {/* Virtual list */}
      <div ref={parentRef} style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
          {rowVirtualizer.getVirtualItems().map(virtualRow => {
            const item = filtered[virtualRow.index]
            const plays = item.view_count ?? item.play_count
            const isUnverified = !item.verified && item.verify_status === 0

            return (
              <div
                key={virtualRow.key}
                data-index={virtualRow.index}
                ref={rowVirtualizer.measureElement}
                onClick={() => handleRowClick(item.url)}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  transform: `translateY(${virtualRow.start}px)`,
                  display: 'grid',
                  gridTemplateColumns: '52px 1fr 90px 100px',
                  alignItems: 'center',
                  padding: '0 12px',
                  height: 44,
                  borderBottom: '1px solid var(--divider)',
                  cursor: 'pointer',
                  transition: 'background-color 0.15s ease',
                }}
                onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#FAFAF9')}
                onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'transparent')}
              >
                <PlatformBadge source={item.source} />
                <span style={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  paddingRight: 12,
                  fontSize: 13,
                }}>
                  {isUnverified && <span title={strings.unverifiedTooltip} style={{ marginRight: 4, fontSize: 11 }}>⚠️</span>}
                  {item.title}
                </span>
                <span style={{ textAlign: 'right', color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'Inter' }}>
                  {formatDate(item.published_at)}
                </span>
                <span style={{ textAlign: 'right', color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'Inter' }}>
                  {formatCount(plays)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
