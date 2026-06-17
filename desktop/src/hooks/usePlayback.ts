import { useEffect, useCallback, useRef } from 'react'
import { usePlayerStore } from '../store/playerStore'
import { useBackend } from './useBackend'
import { audioEngine } from '../lib/audioEngine'
import { useKeyboard } from './useKeyboard'

export function usePlayback() {
  const {
    songs,
    currentIndex,
    playbackState,
    currentTime,
    duration,
    volume,
    isMuted,
    currentSong,
    lyrics,
    currentLyricIndex,
    setPlaybackState,
    setCurrentTime,
    setVolume,
    toggleMute,
    play,
    next,
    prev,
  } = usePlayerStore()

  const { fetchQueue, fetchAndPlay, fetchLyrics, syncLyricIndex, connectWS } = useBackend()

  const initRef = useRef(false)
  const autoPlayRef = useRef(false)

  // ── Initialize: fetch queue, select first song (don't play — wait for user) ──
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    fetchQueue().then((data) => {
      if (data && data.songs.length > 0) {
        // Select first song for display, but don't auto-play
        usePlayerStore.getState().play(0)
      }
    })
    connectWS()
  }, [fetchQueue, connectWS])

  // ── Play when song changes (only if user-initiated or auto-next) ──
  useEffect(() => {
    if (currentSong && currentIndex >= 0 && autoPlayRef.current) {
      fetchAndPlay(currentSong)
      fetchLyrics(currentSong.id)
    }
  }, [currentIndex, currentSong?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Sync lyrics every 300ms ──
  useEffect(() => {
    if (playbackState !== 'playing') return
    const interval = setInterval(() => {
      syncLyricIndex(usePlayerStore.getState().currentTime * 1000)
    }, 300)
    return () => clearInterval(interval)
  }, [playbackState, syncLyricIndex])

  // ── Dwell detection: trigger smart-insert when >80% listened ──
  const DWELL_THRESHOLD = 0.8
  const dwellFiredRef = useRef<number | null>(null)
  // Reset dwell flag when song changes
  useEffect(() => { dwellFiredRef.current = null }, [currentSong?.id])
  useEffect(() => {
    if (playbackState !== 'playing' || !currentSong || duration <= 0) return
    const pct = currentTime / duration
    if (pct > DWELL_THRESHOLD && dwellFiredRef.current !== currentSong.id) {
      dwellFiredRef.current = currentSong.id
      fetch('/api/smart-insert', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger: 'dwell' }),
      }).then(r => r.json()).then(data => {
        if (data.inserted?.length) {
          const curSongs = [...usePlayerStore.getState().songs]
          const idx = usePlayerStore.getState().currentIndex
          curSongs.splice(idx + 1, 0, ...data.inserted)
          usePlayerStore.getState().setSongs(curSongs)
        }
      }).catch(() => {})
    }
  }, [currentTime, duration, playbackState, currentSong?.id])

  // ── Keyboard shortcuts ──
  useKeyboard({
    Space: () => togglePlay(),
    ArrowLeft: () => prevSong(),
    ArrowRight: () => nextSong(),
    ArrowUp: () => setVolume(Math.min(1.5, volume + 0.05)),
    ArrowDown: () => setVolume(Math.max(0, volume - 0.05)),
    KeyL: () => handleLike(),
    KeyS: () => handleSkip(),
  })

  // ── Actions ──
  const togglePlay = useCallback(() => {
    if (playbackState === 'playing') {
      audioEngine.togglePlay()
      setPlaybackState('paused')
    } else if (playbackState === 'paused') {
      audioEngine.togglePlay()
      setPlaybackState('playing')
    } else {
      // First play — enable auto-play for future song changes
      autoPlayRef.current = true
      const s = usePlayerStore.getState().currentSong
      if (s) {
        fetchAndPlay(s)
        fetchLyrics(s.id)
      }
    }
  }, [playbackState, setPlaybackState, fetchAndPlay, fetchLyrics])

  const nextSong = useCallback(() => {
    autoPlayRef.current = true
    next()
  }, [next])

  const prevSong = useCallback(() => {
    autoPlayRef.current = true
    prev()
  }, [prev])

  const seekTo = useCallback(
    (time: number) => {
      audioEngine.seek(time)
      setCurrentTime(time)
    },
    [setCurrentTime]
  )

  const changeVolume = useCallback(
    (vol: number) => {
      setVolume(vol)
      audioEngine.setVolume(vol)
    },
    [setVolume]
  )

  const toggleMuteAudio = useCallback(() => {
    toggleMute()
    audioEngine.toggleMute()
  }, [toggleMute])

  const handleLike = useCallback(async () => {
    const s = usePlayerStore.getState()
    if (!s.currentSong) return
    fetch(`/api/like/${s.currentSong.id}`, { method: 'POST' }).catch(() => {})
    s.setShaderMood('excited')
    setTimeout(() => s.setShaderMood('normal'), 3000)
    // Smart insert: 2 similar songs after like
    try {
      const res = await fetch('/api/smart-insert', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger: 'like' }),
      })
      const data = await res.json()
      if (data.inserted?.length) {
        const curSongs = [...usePlayerStore.getState().songs]
        const idx = usePlayerStore.getState().currentIndex
        curSongs.splice(idx + 1, 0, ...data.inserted)
        usePlayerStore.getState().setSongs(curSongs)
      }
    } catch {}
  }, [])

  const handleSkip = useCallback(async () => {
    const s = usePlayerStore.getState()
    if (s.currentSong) {
      // Smart insert: 2 different songs after skip
      try {
        const res = await fetch('/api/smart-insert', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ trigger: 'skip' }),
        })
        const data = await res.json()
        if (data.inserted?.length) {
          const curSongs = [...usePlayerStore.getState().songs]
          const idx = usePlayerStore.getState().currentIndex
          curSongs.splice(idx + 1, 0, ...data.inserted)
          usePlayerStore.getState().setSongs(curSongs)
        }
      } catch {}
    }
    nextSong()
  }, [nextSong])

  return {
    // State
    songs,
    currentIndex,
    playbackState,
    currentTime,
    duration,
    volume,
    isMuted,
    currentSong,
    lyrics,
    currentLyricIndex,

    // Actions
    togglePlay,
    nextSong,
    prevSong,
    seekTo,
    changeVolume,
    toggleMuteAudio,
    handleLike,
    handleSkip,
    play,
  }
}
