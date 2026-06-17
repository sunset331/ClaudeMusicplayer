export const COLORS = {
  bg: '#020203',
  surface: '#08080c',
  glass: {
    bg: 'rgba(255,255,255,0.03)',
    border: 'rgba(255,255,255,0.08)',
    highlight: 'rgba(255,255,255,0.06)',
  },
  pigment: {
    red: [1.0, 0.08, 0.02] as [number, number, number],
    blue: [0.02, 0.10, 0.95] as [number, number, number],
    yellow: [1.0, 0.87, 0.05] as [number, number, number],
  },
  text: {
    primary: '#F5F0FF',
    secondary: '#B8A8D8',
    muted: '#706090',
  },
  accent: {
    rose: '#F0A8C0',
    lavender: '#C084FC',
  },
} as const

export const BLUR = {
  panel: 'blur(40px)',
  heavy: 'blur(80px)',
} as const

export const SPRINGS = {
  gentle: { type: 'spring' as const, stiffness: 40, damping: 25 },
  snappy: { type: 'spring' as const, stiffness: 200, damping: 20 },
  slow: { type: 'spring' as const, stiffness: 20, damping: 30 },
  lyricEnter: { type: 'spring' as const, stiffness: 60, damping: 18 },
  lyricExit: { type: 'spring' as const, stiffness: 30, damping: 22 },
}

export const SPEED_CONFIG = {
  slow: { label: '慢', speed: 0.3, blobMoveScale: 0.0001 },
  medium: { label: '中', speed: 0.6, blobMoveScale: 0.00025 },
  fast: { label: '快', speed: 1.0, blobMoveScale: 0.0005 },
} as const
