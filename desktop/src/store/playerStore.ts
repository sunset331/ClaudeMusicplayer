import { create } from 'zustand'
import type { Song, LyricLine, PlaybackState, AppMode, FluidSpeed, ShaderMood } from '../types'

interface PlayerStore {
  // ── Queue ──
  songs: Song[]
  currentIndex: number
  mode: AppMode
  setSongs: (songs: Song[]) => void
  setMode: (mode: AppMode) => void

  // ── Playback ──
  playbackState: PlaybackState
  currentTime: number
  duration: number
  volume: number
  isMuted: boolean
  setPlaybackState: (state: PlaybackState) => void
  setCurrentTime: (time: number) => void
  setDuration: (dur: number) => void
  setVolume: (vol: number) => void
  toggleMute: () => void

  // ── Current song ──
  currentSong: Song | null
  setCurrentSong: (song: Song | null) => void

  // ── Lyrics ──
  lyrics: LyricLine[]
  currentLyricIndex: number
  setLyrics: (lyrics: LyricLine[]) => void
  setCurrentLyricIndex: (idx: number) => void

  // ── Fluid Background ──
  fluidSpeed: FluidSpeed
  shaderMood: ShaderMood
  setFluidSpeed: (speed: FluidSpeed) => void
  setShaderMood: (mood: ShaderMood) => void

  // ── Stats ──
  playCount: number
  likeCount: number
  skipCount: number
  setPlayCount: (n: number) => void
  incrementPlayCount: () => void

  // ── Play actions ──
  play: (index: number) => void
  next: () => void
  prev: () => void
}

export const usePlayerStore = create<PlayerStore>((set, get) => ({
  songs: [],
  currentIndex: -1,
  mode: 'rap',
  setSongs: (songs) => set({ songs }),
  setMode: (mode) => set({ mode }),

  playbackState: 'idle',
  currentTime: 0,
  duration: 0,
  volume: 1.0,
  isMuted: false,
  setPlaybackState: (playbackState) => set({ playbackState }),
  setCurrentTime: (currentTime) => set({ currentTime }),
  setDuration: (duration) => set({ duration }),
  setVolume: (volume) => set({ volume }),
  toggleMute: () => set((s) => ({ isMuted: !s.isMuted })),

  currentSong: null,
  setCurrentSong: (currentSong) => set({ currentSong }),

  lyrics: [],
  currentLyricIndex: -1,
  setLyrics: (lyrics) => set({ lyrics, currentLyricIndex: -1 }),
  setCurrentLyricIndex: (currentLyricIndex) => set({ currentLyricIndex }),

  fluidSpeed: 'medium',
  shaderMood: 'normal',
  setFluidSpeed: (fluidSpeed) => set({ fluidSpeed }),
  setShaderMood: (shaderMood) => set({ shaderMood }),

  playCount: 0,
  likeCount: 0,
  skipCount: 0,
  setPlayCount: (playCount) => set({ playCount }),
  incrementPlayCount: () => set((s) => ({ playCount: s.playCount + 1 })),

  play: (index) => {
    const { songs } = get()
    if (index >= 0 && index < songs.length) {
      set({ currentIndex: index, currentSong: songs[index], currentTime: 0, currentLyricIndex: -1 })
    }
  },
  next: () => {
    const { songs, currentIndex } = get()
    const nextIdx = (currentIndex + 1) % songs.length
    if (songs[nextIdx]) {
      set({ currentIndex: nextIdx, currentSong: songs[nextIdx], currentTime: 0, currentLyricIndex: -1 })
    }
  },
  prev: () => {
    const { songs, currentIndex } = get()
    const prevIdx = currentIndex <= 0 ? songs.length - 1 : currentIndex - 1
    if (songs[prevIdx]) {
      set({ currentIndex: prevIdx, currentSong: songs[prevIdx], currentTime: 0, currentLyricIndex: -1 })
    }
  },
}))
