export const strings = {
  // Layout
  siteTitle: '田馥甄檔案庫 · Hebe Tien Archive',
  defaultTitle: '田馥甄檔案庫',
  footerText: '資料來源：YouTube · Bilibili · Google Search',
  footerUpdate: '持續更新',

  // Home
  eyebrow: 'ARCHIVE · 田馥甄',
  heroName: '田馥甄',
  heroNameEn: 'Hebe Tien',
  heroMeta: '1983 · 台灣 · 華語流行 · 金曲獎最佳女歌手',
  statTotal: '收錄總數',
  statPlatform: '雙平台',
  statUpdate: '持續更新',

  // Sidebar
  sidebarBrand: '田馥甄',
  sidebarSubtitle: 'Hebe Tien Archive',
  sidebarCount: (n: number) => `共收錄 ${n} 條`,
  mobileHome: '首頁',

  // Categories
  categories: {
    personalMV: { label: '個人 MV', sub: 'Official MV & Lyric Video', search: '搜尋個人 MV...' },
    sheMV:      { label: 'S.H.E MV', sub: 'S.H.E 時期全作品', search: '搜尋 S.H.E MV...' },
    concerts:   { label: '演唱會', sub: 'Concert & Live', search: '搜尋演唱會...' },
    variety:    { label: '綜藝節目', sub: 'TV Shows & Variety', search: '搜尋綜藝節目...' },
    interviews: { label: '採訪訪談', sub: 'Interviews & Press', search: '搜尋採訪訪談...' },
    singles:    { label: '影視單曲', sub: 'OST & Singles', search: '搜尋影視單曲...' },
    collabs:    { label: '合唱合作', sub: 'Collabs & Features', search: '搜尋合唱合作...' },
  },

  // ContentTable
  searchPlaceholder: '搜尋標題...',
  filterAll: '全部',
  tableHeaderPlatform: '平台',
  tableHeaderTitle: '標題',
  tableHeaderDate: '日期',
  tableHeaderPlays: '播放量',
  showCount: (shown: number, total: number) => `顯示 ${shown} 條，共 ${total} 條`,
  unverifiedTooltip: '連結未驗證',
  feedbackForm: '意見回饋（Google 表單）',
  feedbackGithub: '問題回報（GitHub Issues）',
  feedbackFormDesc: '補充遺漏影片、更正錯誤資料',
  feedbackGithubDesc: '回報網站 Bug、提出功能建議',

  // Number formatting
  yi: '億',
  qianwan: '千萬',
  wan: '萬',
} as const
