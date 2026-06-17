export interface Song {
  id: number
  name: string
  artist: string
  album: string
  albumId: number
  duration: number
  score: number
  sources: string[]
  url?: string
  played: boolean
  scoreBreakdown?: Record<string, number>
}

export interface LyricLine {
  time: number
  text: string
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
}

export type PlaybackState = 'idle' | 'loading' | 'playing' | 'paused'
export type AppMode = 'rap' | 'mixed'
export type FluidSpeed = 'slow' | 'medium' | 'fast'
export type ShaderMood = 'normal' | 'excited' | 'calm'
export type DisplayMode = 'pigment' | 'soft'

export interface PlayerState {
  // Queue
  songs: Song[]
  currentIndex: number
  mode: AppMode

  // Playback
  playbackState: PlaybackState
  currentTime: number
  duration: number
  volume: number
  isMuted: boolean

  // Lyrics
  lyrics: LyricLine[]
  currentLyricIndex: number

  // Fluid background
  fluidSpeed: FluidSpeed
  shaderMood: ShaderMood

  // Stats
  playCount: number
  likeCount: number
  skipCount: number
}

export interface BackendStatus {
  mode: AppMode
  epsilon: number
  songCount: number
  loginStatus: boolean
}
