import { Component, type ReactNode, useState, useCallback } from 'react'
import { usePlayerStore } from './store/playerStore'
import { usePlayback } from './hooks/usePlayback'
import FluidBackground from './components/Background/FluidBackground'
import TopBar from './components/TopBar'
import LyricsCanvas from './components/Lyrics/LyricsCanvas'
import ProgressBar from './components/Controls/ProgressBar'
import PlayControls from './components/Controls/PlayControls'
import VolumeControl from './components/Controls/VolumeControl'
import QueuePanel from './components/Queue/QueuePanel'
import ChatPanel from './components/Chat/ChatPanel'
import ScorePanel from './components/Score/ScorePanel'
import { ListMusic, MessageCircle } from 'lucide-react'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  constructor(props: { children: ReactNode }) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ width: '100vw', height: '100vh', background: '#020203', display: 'flex',
          flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          color: '#F5F0FF', fontFamily: 'Inter, sans-serif', padding: 48 }}>
          <h1 style={{ fontSize: '1.5rem', marginBottom: 16, fontWeight: 500 }}>Something went wrong</h1>
          <pre style={{ color: '#B8A8D8', fontSize: '0.8rem', maxWidth: 600, whiteSpace: 'pre-wrap',
            background: 'rgba(255,255,255,0.05)', padding: 20, borderRadius: 12 }}>
            {this.state.error.message}{'\n\n'}{this.state.error.stack}</pre>
        </div>
      )
    }
    return this.props.children
  }
}

function PlayerUI() {
  const fluidSpeed = usePlayerStore((s) => s.fluidSpeed)
  const setFluidSpeed = usePlayerStore((s) => s.setFluidSpeed)
  const playCount = usePlayerStore((s) => s.playCount)
  const songs = usePlayerStore((s) => s.songs)
  const currentIndex = usePlayerStore((s) => s.currentIndex)
  const mode = usePlayerStore((s) => s.mode)
  const setMode = usePlayerStore((s) => s.setMode)

  const [showQueue, setShowQueue] = useState(false)
  const [showChat, setShowChat] = useState(false)

  const {
    playbackState, currentTime, duration, volume, isMuted,
    lyrics, currentLyricIndex, currentSong,
    togglePlay, nextSong, prevSong, play,
    seekTo, changeVolume, toggleMuteAudio, handleLike,
  } = usePlayback()

  const switchMode = useCallback(async (newMode: 'rap' | 'mixed') => {
    await fetch('/api/mode', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: newMode }) })
    setMode(newMode)
    const res = await fetch('/api/queue')
    usePlayerStore.getState().setSongs((await res.json()).songs)
  }, [setMode])

  const addToPlaylist = useCallback(async () => {
    if (!currentSong) return
    fetch(`/api/playlist/add/${currentSong.id}`, { method: 'POST' }).catch(() => {})
  }, [currentSong])

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative', overflow: 'hidden',
      display: 'flex', flexDirection: 'column', background: '#020203' }}>
      <FluidBackground speed={fluidSpeed} mood={usePlayerStore((s) => s.shaderMood)} />

      {/* Frosted glass overlay */}
      <div className="glass-overlay" style={{ position: 'fixed', inset: 0, zIndex: 1, pointerEvents: 'none' }} />

      {/* UI Layer */}
      <div style={{ position: 'relative', zIndex: 10, display: 'flex',
        flexDirection: 'column', height: '100%', width: '100%' }}>

        {/* Top bar: time + speed + mode */}
        <TopBar fluidSpeed={fluidSpeed} onSpeedChange={setFluidSpeed}
          playCount={playCount} mode={mode} onModeChange={switchMode} />

        {/* Floating action buttons */}
        <div style={{ position: 'absolute', left: 20, top: 72, zIndex: 20, display: 'flex', gap: 8 }}>
          <button onClick={() => setShowQueue(!showQueue)}
            style={iconBtnStyle} aria-label="播放列表">
            <ListMusic size={16} />
          </button>
        </div>

        <div style={{ position: 'absolute', right: 20, top: 72, zIndex: 20 }}>
          {!showChat && (
            <button onClick={() => setShowChat(true)}
              style={iconBtnStyle} aria-label="AI 聊天">
              <MessageCircle size={16} />
            </button>
          )}
        </div>

        {/* Score panel */}
        <ScorePanel song={currentSong} />

        {/* Chat panel */}
        <ChatPanel isOpen={showChat} onClose={() => setShowChat(false)} />

        {/* Center: Lyrics */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center',
          justifyContent: 'center', padding: '0 64px' }}>
          <LyricsCanvas
            lyrics={lyrics} currentIndex={currentLyricIndex}
            isPlaying={playbackState === 'playing'}
            currentSong={currentSong ? { name: currentSong.name, artist: currentSong.artist } : undefined} />
        </div>

        {/* Bottom controls */}
        <div style={{ padding: '20px 48px 24px', display: 'flex',
          flexDirection: 'column', alignItems: 'center', gap: 14 }}>
          <ProgressBar currentTime={currentTime} duration={duration}
            onSeek={seekTo} disabled={playbackState === 'idle' || playbackState === 'loading'} />
          <PlayControls playbackState={playbackState}
            onToggle={togglePlay} onPrev={prevSong} onNext={nextSong}
            disabled={playbackState === 'loading'} />

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <VolumeControl volume={volume} isMuted={isMuted}
              onVolumeChange={changeVolume} onMuteToggle={toggleMuteAudio} />

            <div style={{ display: 'flex', gap: 8 }}>
              <button style={actionBtnStyle} onClick={handleLike}>♥ 喜欢</button>
              <button style={actionBtnStyle} onClick={addToPlaylist}>+ 歌单</button>
              <button style={actionBtnStyle} onClick={nextSong}>» 跳过</button>
            </div>
          </div>

          {currentSong && (
            <div style={{ textAlign: 'center', paddingBottom: 4 }}>
              <span style={{ color: '#706090', fontSize: '0.7rem' }}>
                {currentSong.artist}{currentSong.album ? ` · ${currentSong.album}` : ''}
              </span>
            </div>
          )}
        </div>
      </div>

      <QueuePanel songs={songs} currentIndex={currentIndex} isOpen={showQueue}
        onClose={() => setShowQueue(false)} onPlay={(i) => { play(i); setShowQueue(false) }} />
    </div>
  )
}

const iconBtnStyle: React.CSSProperties = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 36, height: 36, borderRadius: '50%',
  border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(255,255,255,0.03)', color: '#B8A8D8',
  cursor: 'pointer', backdropFilter: 'blur(20px)',
  WebkitBackdropFilter: 'blur(20px)',
}

const actionBtnStyle: React.CSSProperties = {
  padding: '6px 16px', borderRadius: 16, border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(255,255,255,0.03)', color: '#B8A8D8',
  fontSize: '0.75rem', fontFamily: 'Inter, sans-serif', cursor: 'pointer',
  backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)',
  transition: 'all 0.2s ease',
}

export default function App() {
  return <ErrorBoundary><PlayerUI /></ErrorBoundary>
}
