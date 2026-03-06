import { useRef, useState, useMemo, useCallback } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import Fuse from 'fuse.js'

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
type Platform = 'all' | 'youtube' | 'bilibili'

function formatCount(n?: number): string {
  if (!n) return '—'
  if (n >= 100_000_000) return (n / 100_000_000).toFixed(1) + '亿'
  if (n >= 10_000_000) return (n / 10_000_000).toFixed(0) + '千万'
  if (n >= 10_000) return (n / 10_000).toFixed(0) + '万'
  return n.toLocaleString()
}

function formatDate(s?: string): string {
  if (!s) return '—'
  return s.slice(0, 7) // YYYY-MM
}

function PlatformBadge({ source }: { source: string }) {
  if (source === 'youtube') {
    return (
      <span style={{
        display: 'inline-block', padding: '1px 6px', borderRadius: 3,
        backgroundColor: '#FEE2E2', color: '#DC2626',
        fontSize: 11, fontWeight: 500, letterSpacing: '0.02em',
        fontFamily: 'Inter, sans-serif',
      }}>YT</span>
    )
  }
  if (source === 'bilibili') {
    return (
      <span style={{
        display: 'inline-block', padding: '1px 6px', borderRadius: 3,
        backgroundColor: '#FCE7F3', color: '#BE185D',
        fontSize: 11, fontWeight: 500, letterSpacing: '0.02em',
        fontFamily: 'Inter, sans-serif',
      }}>BL</span>
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

export default function ContentTable({ items, searchPlaceholder = '搜索标题...' }: Props) {
  const [query, setQuery] = useState('')
  const [platform, setPlatform] = useState<Platform>('all')
  const [sort, setSort] = useState<SortKey>('date')
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

    result.sort((a, b) => {
      if (sort === 'date') {
        return (b.published_at ?? '').localeCompare(a.published_at ?? '')
      }
      const pa = (a.view_count ?? a.play_count ?? 0)
      const pb = (b.view_count ?? b.play_count ?? 0)
      return pb - pa
    })

    return result
  }, [query, platform, sort, fuse, items])

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
    padding: '4px 12px',
    borderRadius: 4,
    border: '1px solid',
    borderColor: active ? 'var(--accent)' : 'var(--divider)',
    backgroundColor: active ? 'var(--accent)' : 'transparent',
    color: active ? '#fff' : 'var(--text-secondary)',
    fontSize: 12,
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  })

  return (
    <div>
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
              {p === 'all' ? `全部 ${items.length}` : p === 'youtube' ? `YT ${ytCount}` : `BL ${blCount}`}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button style={btnStyle(sort === 'date')} onClick={() => setSort('date')}>最新</button>
          <button style={btnStyle(sort === 'plays')} onClick={() => setSort('plays')}>最多播放</button>
        </div>
      </div>

      {/* Count */}
      <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginBottom: 8 }}>
        显示 {filtered.length} 条，共 {items.length} 条
      </div>

      {/* Table header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '52px 1fr 80px 80px',
        padding: '8px 12px',
        borderBottom: '1px solid var(--divider)',
        borderTop: '1px solid var(--divider)',
        color: 'var(--text-secondary)',
        fontSize: 12,
        fontWeight: 500,
        letterSpacing: '0.03em',
      }}>
        <span>平台</span>
        <span>标题</span>
        <span style={{ textAlign: 'right' }}>日期</span>
        <span style={{ textAlign: 'right' }}>播放量</span>
      </div>

      {/* Virtual list */}
      <div ref={parentRef} style={{ height: 600, overflowY: 'auto' }}>
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
                  gridTemplateColumns: '52px 1fr 80px 80px',
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
                  {isUnverified && <span title="链接未验证" style={{ marginRight: 4, fontSize: 11 }}>⚠️</span>}
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
