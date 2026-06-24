import { Component, type ReactNode, useState, useCallback, useEffect } from 'react'
import { usePlayerStore } from './store/playerStore'
import { usePlayback } from './hooks/usePlayback'
import FluidBackground from './components/Background/FluidBackground'
import TopBar from './components/TopBar'
import ProgressBar from './components/Controls/ProgressBar'
import PlayControls from './components/Controls/PlayControls'
import QueuePanel from './components/Queue/QueuePanel'
import { Play, SkipForward, SkipBack, Heart, Plus, RefreshCw, Monitor, Smartphone } from 'lucide-react'

// ── Web Remote Console ────────────────────────────────────────────
// Lightweight remote control + now-playing dashboard.
// The native tkinter app (app.py) is the primary playback engine;
// this web console serves as a remote control for mobile/tablet.
// ───────────────────────────────────────────────────────────────────

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  constructor(props: { children: ReactNode }) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ width: '100vw', height: '100vh', background: '#020203', display: 'flex',
          flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          color: '#F5F0FF', fontFamily: 'Inter, sans-serif', padding: 48 }}>
          <h1 style={{ fontSize: '1.5rem', marginBottom: 16, fontWeight: 500 }}>远程控制台 · 连接中断</h1>
          <p style={{ color: '#B8A8D8', fontSize: '0.85rem' }}>请确认桌面应用正在运行</p>
          <pre style={{ color: '#706090', fontSize: '0.7rem', maxWidth: 600, whiteSpace: 'pre-wrap',
            background: 'rgba(255,255,255,0.05)', padding: 20, borderRadius: 12 }}>
            {this.state.error.message}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}

function RemoteConsole() {
  const fluidSpeed = usePlayerStore((s) => s.fluidSpeed)
  const setFluidSpeed = usePlayerStore((s) => s.setFluidSpeed)
  const songs = usePlayerStore((s) => s.songs)
  const currentIndex = usePlayerStore((s) => s.currentIndex)
  const mode = usePlayerStore((s) => s.mode)
  const setMode = usePlayerStore((s) => s.setMode)
  const displayMode = usePlayerStore((s) => s.displayMode)
  const setDisplayMode = usePlayerStore((s) => s.setDisplayMode)

  const [showQueue, setShowQueue] = useState(false)
  const [serverStatus, setServerStatus] = useState<'connected' | 'disconnected'>('disconnected')
  const [nowPlaying, setNowPlaying] = useState<{songname?: string; singers?: string} | null>(null)

  const {
    playbackState, currentTime, duration, currentSong,
    togglePlay, nextSong, prevSong,
    seekTo, handleLike,
  } = usePlayback()

  // ── Poll server status ──────────────────────────────────────
  useEffect(() => {
    const poll = async () => {
      try {
        const r = await fetch('/api/status')
        if (r.ok) {
          setServerStatus('connected')
          // Also poll now-playing from session bridge
          try {
            const np = await fetch('/api/now-playing')
            if (np.ok) setNowPlaying(await np.json())
          } catch {}
        } else {
          setServerStatus('disconnected')
        }
      } catch {
        setServerStatus('disconnected')
      }
    }
    poll()
    const id = setInterval(poll, 5000)
    return () => clearInterval(id)
  }, [])

  // ── Mode switch ─────────────────────────────────────────────
  const switchMode = useCallback(async (newMode: 'rap' | 'mixed' | 'focus') => {
    await fetch('/api/mode', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: newMode }) })
    setMode(newMode)
    const res = await fetch('/api/queue')
    usePlayerStore.getState().setSongs((await res.json()).songs)
  }, [setMode])

  // ── Refresh candidates ──────────────────────────────────────
  const refreshCandidates = useCallback(async () => {
    await fetch('/api/rebuild', { method: 'POST' })
    const res = await fetch('/api/queue')
    usePlayerStore.getState().setSongs((await res.json()).songs)
  }, [])

  const addToPlaylist = useCallback(async () => {
    if (!currentSong) return
    fetch(`/api/playlist/add/${currentSong.id}`, { method: 'POST' }).catch(() => {})
  }, [currentSong])

  const MODES = ['rap', 'mixed', 'focus'] as const
  const MODE_LABELS: Record<string, string> = { rap: 'RAP', mixed: 'Mixed', focus: 'Focus' }

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', overflow: 'hidden',
      display: 'flex', flexDirection: 'column', background: '#020203' }}>
      <FluidBackground speed={fluidSpeed} mood={usePlayerStore((s) => s.shaderMood)} displayMode={displayMode} />

      {displayMode === 'pigment' && (
        <div className="glass-overlay" style={{ position: 'fixed', inset: 0, zIndex: 1, pointerEvents: 'none' }} />
      )}

      {/* UI Layer */}
      <div style={{ position: 'relative', zIndex: 10, display: 'flex',
        flexDirection: 'column', height: '100%', width: '100%', maxWidth: 480, margin: '0 auto' }}>

        {/* ── Header: status dot + device hint ── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px 8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%',
              background: serverStatus === 'connected' ? '#4ecca3' : '#ff8a80',
              display: 'inline-block' }} />
            <span style={{ color: '#706090', fontSize: '0.75rem', fontFamily: 'Inter' }}>
              {serverStatus === 'connected' ? '已连接' : '未连接'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Monitor size={14} color="#706090" />
            <span style={{ color: '#504070', fontSize: '0.65rem' }}>远程控制台</span>
          </div>
        </div>

        {/* ── Now Playing Card ── */}
        <div style={{ margin: '8px 20px', padding: 20, borderRadius: 16,
          background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)',
          backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }}>
          {currentSong ? (
            <>
              <h2 style={{ color: '#F5F0FF', fontSize: '1.1rem', fontWeight: 500, margin: 0 }}>
                {currentSong.name}
              </h2>
              <p style={{ color: '#B8A8D8', fontSize: '0.85rem', margin: '4px 0 0' }}>
                {currentSong.artist}
              </p>
            </>
          ) : (
            <p style={{ color: '#706090', fontSize: '0.85rem', margin: 0 }}>
              {serverStatus === 'connected' ? '等待播放...' : '请启动桌面应用'}
            </p>
          )}

          {/* Mode pills */}
          <div style={{ display: 'flex', gap: 6, marginTop: 14 }}>
            {MODES.map(m => (
              <button key={m} onClick={() => switchMode(m)}
                style={{
                  padding: '4px 14px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.1)',
                  background: mode === m ? 'rgba(192,132,252,0.2)' : 'transparent',
                  color: mode === m ? '#c084fc' : '#706090',
                  fontSize: '0.7rem', cursor: 'pointer', fontFamily: 'Inter',
                  transition: 'all 0.2s',
                }}>
                {MODE_LABELS[m]}
              </button>
            ))}
            <button onClick={refreshCandidates}
              style={{ marginLeft: 'auto', padding: '4px 10px', borderRadius: 12,
                border: '1px solid rgba(255,255,255,0.08)', background: 'transparent',
                color: '#706090', fontSize: '0.7rem', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 4 }}>
              <RefreshCw size={12} /> 刷新
            </button>
          </div>
        </div>

        {/* ── Progress ── */}
        <div style={{ padding: '0 20px', marginTop: 8 }}>
          <ProgressBar currentTime={currentTime} duration={duration}
            onSeek={seekTo} disabled={playbackState === 'idle' || playbackState === 'loading'} />
        </div>

        {/* ── Big Play Controls (mobile-friendly) ── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 32, padding: '16px 20px' }}>
          <button onClick={prevSong} style={ctrlBtnStyle} aria-label="上一首">
            <SkipBack size={24} />
          </button>
          <button onClick={togglePlay} style={{
            ...ctrlBtnStyle, width: 64, height: 64, borderRadius: '50%',
            background: 'rgba(192,132,252,0.15)', border: '2px solid rgba(192,132,252,0.3)',
          }} aria-label="播放/暂停">
            <Play size={28} fill={playbackState === 'playing' ? '#c084fc' : 'none'}
              color="#c084fc" />
          </button>
          <button onClick={nextSong} style={ctrlBtnStyle} aria-label="下一首">
            <SkipForward size={24} />
          </button>
        </div>

        {/* ── Action buttons ── */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 12, padding: '0 20px' }}>
          <button style={actionBtnStyle} onClick={handleLike}>♥ 喜欢</button>
          <button style={actionBtnStyle} onClick={addToPlaylist}>+ 歌单</button>
          <button style={actionBtnStyle} onClick={() => setShowQueue(!showQueue)}>
            {showQueue ? '隐藏队列' : '播放列表'}
          </button>
        </div>

        {/* ── Connection hint ── */}
        <div style={{ marginTop: 'auto', padding: '12px 20px', textAlign: 'center' }}>
          <p style={{ color: '#403060', fontSize: '0.65rem', margin: 0 }}>
            桌面应用 (app.py) 为主播放引擎 · 本页面为远程控制台
          </p>
        </div>
      </div>

      {/* ── Queue panel (slide-up) ── */}
      <QueuePanel songs={songs} currentIndex={currentIndex} isOpen={showQueue}
        onClose={() => setShowQueue(false)} onPlay={(i) => {
          usePlayerStore.getState().play?.(i)
          setShowQueue(false)
        }} />
    </div>
  )
}

const ctrlBtnStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 48, height: 48, borderRadius: '50%',
  border: 'none', background: 'transparent', color: '#B8A8D8',
  cursor: 'pointer',
}

const actionBtnStyle: React.CSSProperties = {
  padding: '8px 20px', borderRadius: 20, border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(255,255,255,0.03)', color: '#B8A8D8',
  fontSize: '0.8rem', fontFamily: 'Inter, sans-serif', cursor: 'pointer',
  backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
  transition: 'all 0.2s ease',
}

export default function App() {
  return <ErrorBoundary><RemoteConsole /></ErrorBoundary>
}
