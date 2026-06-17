import { Component, type ReactNode } from 'react'
import { usePlayerStore } from './store/playerStore'
import { usePlayback } from './hooks/usePlayback'
import FluidBackground from './components/Background/FluidBackground'
import TopBar from './components/TopBar'
import LyricsCanvas from './components/Lyrics/LyricsCanvas'
import ProgressBar from './components/Controls/ProgressBar'
import PlayControls from './components/Controls/PlayControls'
import VolumeControl from './components/Controls/VolumeControl'

// Error boundary to catch rendering errors
class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error) {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          width: '100vw', height: '100vh', background: '#020203',
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          color: '#F5F0FF', fontFamily: 'Inter, sans-serif', padding: 48,
        }}>
          <h1 style={{ color: '#FF1413', fontSize: '1.5rem', marginBottom: 16 }}>
            Render Error
          </h1>
          <pre style={{
            color: '#B8A8D8', fontSize: '0.85rem',
            maxWidth: 600, whiteSpace: 'pre-wrap',
            background: 'rgba(255,255,255,0.05)', padding: 20,
            borderRadius: 12, border: '1px solid rgba(255,255,255,0.1)',
          }}>
            {this.state.error.message}
            {'\n\n'}
            {this.state.error.stack}
          </pre>
        </div>
      )
    }
    return this.props.children
  }
}

function PlayerUI() {
  const fluidSpeed = usePlayerStore((s) => s.fluidSpeed)
  const shaderMood = usePlayerStore((s) => s.shaderMood)
  const setFluidSpeed = usePlayerStore((s) => s.setFluidSpeed)
  const playCount = usePlayerStore((s) => s.playCount)

  const {
    playbackState, currentTime, duration, volume, isMuted,
    lyrics, currentLyricIndex, currentSong,
    togglePlay, nextSong, prevSong,
    seekTo, changeVolume, toggleMuteAudio,
  } = usePlayback()

  return (
    <div style={{
      width: '100vw', height: '100vh', position: 'relative', overflow: 'hidden',
      display: 'flex', flexDirection: 'column', background: '#020203',
    }}>
      <FluidBackground speed={fluidSpeed} mood={shaderMood} />

      <div style={{
        position: 'fixed', inset: 0, zIndex: 1,
        background: 'rgba(2,2,3,0.15)',
        backdropFilter: 'blur(80px)',
        WebkitBackdropFilter: 'blur(80px)',
        pointerEvents: 'none',
      }} />

      <div style={{
        position: 'relative', zIndex: 10, display: 'flex',
        flexDirection: 'column', height: '100%', width: '100%',
      }}>
        <TopBar fluidSpeed={fluidSpeed} onSpeedChange={setFluidSpeed} playCount={playCount} />

        <div style={{
          flex: 1, display: 'flex', alignItems: 'center',
          justifyContent: 'center', padding: '0 48px',
        }}>
          <LyricsCanvas
            lyrics={lyrics}
            currentIndex={currentLyricIndex}
            isPlaying={playbackState === 'playing'}
            currentSong={currentSong ? { name: currentSong.name, artist: currentSong.artist } : undefined}
          />
        </div>

        <div style={{
          padding: '24px 48px 32px', display: 'flex',
          flexDirection: 'column', alignItems: 'center', gap: 20,
        }}>
          <ProgressBar currentTime={currentTime} duration={duration}
            onSeek={seekTo} disabled={playbackState === 'idle' || playbackState === 'loading'} />
          <PlayControls playbackState={playbackState}
            onToggle={togglePlay} onPrev={prevSong} onNext={nextSong}
            disabled={playbackState === 'loading'} />
          <VolumeControl volume={volume} isMuted={isMuted}
            onVolumeChange={changeVolume} onMuteToggle={toggleMuteAudio} />
        </div>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <PlayerUI />
    </ErrorBoundary>
  )
}
