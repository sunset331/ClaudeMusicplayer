import { useEffect, useCallback, useRef, useMemo } from 'react'
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

  const { fetchQueue, fetchAndPlay, fetchLyrics, syncLyricIndex, connectWS, smartInsert } = useBackend()

  const initRef = useRef(false)
  const autoPlayRef = useRef(false)
  const fetchAndPlayRef = useRef(fetchAndPlay)
  const fetchLyricsRef = useRef(fetchLyrics)
  fetchAndPlayRef.current = fetchAndPlay
  fetchLyricsRef.current = fetchLyrics

  // ── Actions (must be before keyboardHandlers — they're referenced by useMemo) ──

  const togglePlay = useCallback(() => {
    if (playbackState === 'playing') {
      audioEngine.togglePlay()
      setPlaybackState('paused')
    } else if (playbackState === 'paused') {
      audioEngine.togglePlay()
      setPlaybackState('playing')
    } else {
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
    smartInsert('like')
  }, [smartInsert])

  const handleSkip = useCallback(async () => {
    const s = usePlayerStore.getState()
    if (s.currentSong) {
      smartInsert('skip')
    }
    nextSong()
  }, [nextSong, smartInsert])

  // ── Keyboard shortcuts ──
  const keyboardHandlers = useMemo(() => ({
    Space: () => togglePlay(),
    ArrowLeft: () => prevSong(),
    ArrowRight: () => nextSong(),
    ArrowUp: () => setVolume(Math.min(1.5, volume + 0.05)),
    ArrowDown: () => setVolume(Math.max(0, volume - 0.05)),
    KeyL: () => handleLike(),
    KeyS: () => handleSkip(),
  }), [togglePlay, prevSong, nextSong, setVolume, volume, handleLike, handleSkip])

  useKeyboard(keyboardHandlers)

  // ── Initialize: fetch queue, select first song (don't play — wait for user) ──
  useEffect(() => {
    if (initRef.current) return
    initRef.current = true

    fetchQueue().then((data) => {
      if (data && data.songs.length > 0) {
        usePlayerStore.getState().play(0)
      }
    })
    connectWS()
  }, [fetchQueue, connectWS])

  // ── Play when song changes (only if user-initiated or auto-next) ──
  useEffect(() => {
    if (currentSong && currentIndex >= 0 && autoPlayRef.current) {
      fetchAndPlayRef.current(currentSong)
      fetchLyricsRef.current(currentSong.id)
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
  useEffect(() => { dwellFiredRef.current = null }, [currentSong?.id])
  useEffect(() => {
    if (playbackState !== 'playing' || !currentSong || duration <= 0) return
    const pct = currentTime / duration
    if (pct > DWELL_THRESHOLD && dwellFiredRef.current !== currentSong.id) {
      dwellFiredRef.current = currentSong.id
      smartInsert('dwell')
    }
  }, [currentTime, duration, playbackState, currentSong?.id])

  return {
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
