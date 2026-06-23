import { useCallback, useRef, useEffect } from 'react'
import { usePlayerStore } from '../store/playerStore'
import { audioEngine } from '../lib/audioEngine'
import type { Song, LyricLine } from '../types'

const API = '/api'

interface QueueResponse {
  songs: Song[]
  mode: string
  epsilon: number
}

export function useBackend() {
  const {
    setSongs,
    setMode,
    setPlaybackState,
    setCurrentTime,
    setDuration,
    setCurrentSong,
    next,
    incrementPlayCount,
    setLyrics,
  } = usePlayerStore()

  const wsRef = useRef<WebSocket | null>(null)
  const lyricsCache = useRef<Map<number, LyricLine[]>>(new Map())

  // ── Fetch song queue from backend ──
  const fetchQueue = useCallback(async () => {
    try {
      const res = await fetch(`${API}/queue`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: QueueResponse = await res.json()
      setSongs(data.songs)
      if (data.mode) setMode(data.mode as 'rap' | 'mixed')
      return data
    } catch (err) {
      console.warn('Backend not available, using demo data:', err)
      // Fallback: demo songs for development without backend
      const demoSongs: Song[] = [
        {
          id: 1, name: '月光', artist: '奏有', album: '月光', albumId: 0,
          duration: 234, score: 0.72, sources: ['artist:奏有'], played: false,
          url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3',
        },
        {
          id: 2, name: 'Rainy Night', artist: 'LoFi Girl', album: 'Chill Beats', albumId: 0,
          duration: 198, score: 0.68, sources: ['genre:lofi'], played: false,
          url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3',
        },
        {
          id: 3, name: 'Starlight', artist: 'Dream Walker', album: 'Midnight', albumId: 0,
          duration: 245, score: 0.65, sources: ['genre:ambient'], played: false,
          url: 'https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3',
        },
      ]
      setSongs(demoSongs)
      return { songs: demoSongs, mode: 'rap', epsilon: 0.15 }
    }
  }, [setSongs, setMode])

  // ── Fetch song URL and play ──
  const cleanupRef = useRef<(() => void) | null>(null)

  const fetchAndPlay = useCallback(
    async (song: Song) => {
      setPlaybackState('loading')

      // Use audio proxy to bypass NetEase Referer restrictions
      const url = `${API}/stream/${song.id}`

      setCurrentSong(song)
      incrementPlayCount()
      // Toast notification
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
        new Notification(song.name, { body: song.artist, silent: true })
      } else if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
        Notification.requestPermission()
      }

      // Remove old callback before registering new one
      cleanupRef.current?.()
      cleanupRef.current = audioEngine.onEvent((event) => {
        switch (event.type) {
          case 'play':
            setPlaybackState('playing')
            setDuration(event.duration ?? 0)
            break
          case 'pause':
            setPlaybackState('paused')
            break
          case 'timeupdate':
            setCurrentTime(event.currentTime ?? 0)
            break
          case 'ended':
            setPlaybackState('idle')
            next()
            break
          case 'error':
            console.error('Audio error:', event.error)
            setPlaybackState('idle')
            break
          case 'loading':
            setPlaybackState('loading')
            break
        }
      })

      audioEngine.play(url)
    },
    [setPlaybackState, setCurrentSong, incrementPlayCount, setCurrentTime, setDuration, next]
  )

  // ── Fetch lyrics ──
  const fetchLyrics = useCallback(
    async (songId: number) => {
      if (lyricsCache.current.has(songId)) {
        setLyrics(lyricsCache.current.get(songId)!)
        return
      }

      try {
        const res = await fetch(`${API}/lyrics/${songId}`)
        if (res.ok) {
          const data = await res.json()
          lyricsCache.current.set(songId, data.lyrics)
          setLyrics(data.lyrics)
        }
      } catch {
        // Demo lyrics for development
        const demoLyrics: LyricLine[] = [
          { time: 0, text: '♪ 器乐演奏 ♪' },
          { time: 5000, text: '夜色轻轻落在窗前' },
          { time: 10000, text: '月光悄悄洒满房间' },
          { time: 15000, text: '思念像雾一般蔓延' },
          { time: 20000, text: '在寂静中缓缓沉淀' },
          { time: 25000, text: '♪ 间奏 ♪' },
          { time: 30000, text: '风吹过旧时的街角' },
          { time: 35000, text: '回忆在灯影里飘摇' },
        ]
        lyricsCache.current.set(songId, demoLyrics)
        setLyrics(demoLyrics)
      }
    },
    [setLyrics]
  )

  // ── Sync lyric index with current time ──
  const syncLyricIndex = useCallback(
    (currentTimeMs: number) => {
      const { lyrics, currentLyricIndex, setCurrentLyricIndex } = usePlayerStore.getState()
      if (lyrics.length === 0) return

      // Find the latest lyric whose time <= currentTimeMs
      let newIdx = -1
      for (let i = lyrics.length - 1; i >= 0; i--) {
        if (lyrics[i].time <= currentTimeMs) {
          newIdx = i
          break
        }
      }

      if (newIdx !== currentLyricIndex) {
        setCurrentLyricIndex(newIdx)
      }
    },
    []
  )

  // ── Connect WebSocket for real-time updates ──
  const connectWS = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => console.log('[WS] Connected')
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'progress') {
            setCurrentTime(msg.currentTime ?? 0)
          }
        } catch {
          // ignore parse errors
        }
      }
      ws.onclose = () => {
        console.log('[WS] Disconnected, reconnecting in 5s...')
        setTimeout(connectWS, 5000)
      }
      ws.onerror = () => ws.close()
    } catch {
      // WebSocket not available
    }
  }, [setCurrentTime])

  // ── Smart insert — deduped helper for dwell/like/skip triggers ──
  const smartInsert = useCallback(async (trigger: 'skip' | 'dwell' | 'like') => {
    try {
      const res = await fetch('/api/smart-insert', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trigger }),
      })
      const data = await res.json()
      if (data.inserted?.length) {
        const store = usePlayerStore.getState()
        const curSongs = [...store.songs]
        curSongs.splice(store.currentIndex + 1, 0, ...data.inserted)
        store.setSongs(curSongs)
      }
    } catch {}
  }, [])

  // ── Cleanup ──
  useEffect(() => {
    return () => {
      wsRef.current?.close()
      cleanupRef.current?.()
      audioEngine.stop()
    }
  }, [])

  return {
    fetchQueue,
    fetchAndPlay,
    fetchLyrics,
    syncLyricIndex,
    connectWS,
    smartInsert,
  }
}
