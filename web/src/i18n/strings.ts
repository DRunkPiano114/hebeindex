export const strings = {
  // Site-level
  siteName: '華語藝人影音誌',

  // Layout
  footerText: '資料來源：YouTube · Bilibili · Google Search',
  footerUpdate: '持續更新',

  // Sidebar
  sidebarCount: (n: number) => `共收錄 ${n} 條`,

  // ContentTable
  searchPlaceholder: '搜尋標題...',
  filterAll: '全部',
  tableHeaderPlatform: '平台',
  tableHeaderTitle: '標題',
  tableHeaderDate: '日期',
  tableHeaderPlays: '播放量',
  showCount: (shown: number, total: number) => `顯示 ${shown} 條，共 ${total} 條`,
  unverifiedTooltip: '連結未驗證',

  // Feedback
  feedbackTitle: '意見回饋',
  feedbackDesc: '補充遺漏影片、更正錯誤資料、回報 Bug、提出建議',
  feedbackGithub: 'GitHub Issues',
  feedbackForm: 'Google 表單',

  // Number formatting
  yi: '億',
  qianwan: '千萬',
  wan: '萬',
} as const
