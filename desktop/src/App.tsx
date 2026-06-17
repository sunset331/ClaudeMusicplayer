import { usePlayerStore } from './store/playerStore'
import { usePlayback } from './hooks/usePlayback'
import FluidBackground from './components/Background/FluidBackground'
import TopBar from './components/TopBar'
import LyricsCanvas from './components/Lyrics/LyricsCanvas'
import ProgressBar from './components/Controls/ProgressBar'
import PlayControls from './components/Controls/PlayControls'
import VolumeControl from './components/Controls/VolumeControl'

export default function App() {
  const fluidSpeed = usePlayerStore((s) => s.fluidSpeed)
  const shaderMood = usePlayerStore((s) => s.shaderMood)
  const setFluidSpeed = usePlayerStore((s) => s.setFluidSpeed)
  const playCount = usePlayerStore((s) => s.playCount)
  const currentSong = usePlayerStore((s) => s.currentSong)

  const {
    playbackState,
    currentTime,
    duration,
    volume,
    isMuted,
    lyrics,
    currentLyricIndex,
    togglePlay,
    nextSong,
    prevSong,
    seekTo,
    changeVolume,
    toggleMuteAudio,
  } = usePlayback()

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--color-bg)',
      }}
    >
      {/* ── Layer 0: Fluid Background (WebGL) ── */}
      <FluidBackground speed={fluidSpeed} mood={shaderMood} />

      {/* ── Layer 1: Glass overlay ambiance ── */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 1,
          background: 'rgba(2,2,3,0.15)',
          backdropFilter: 'blur(80px)',
          WebkitBackdropFilter: 'blur(80px)',
          pointerEvents: 'none',
        }}
      />

      {/* ── Layer 2: Main UI ── */}
      <div
        style={{
          position: 'relative',
          zIndex: 10,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          width: '100%',
        }}
      >
        {/* Top: Time + Speed control */}
        <TopBar
          fluidSpeed={fluidSpeed}
          onSpeedChange={setFluidSpeed}
          playCount={playCount}
        />

        {/* Center: Lyrics Canvas (~60% height) */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '0 48px',
          }}
        >
          <LyricsCanvas
            lyrics={lyrics}
            currentIndex={currentLyricIndex}
            isPlaying={playbackState === 'playing'}
            currentSong={
              currentSong
                ? { name: currentSong.name, artist: currentSong.artist }
                : undefined
            }
          />
        </div>

        {/* Bottom: Controls (~25% height) */}
        <div
          style={{
            padding: '24px 48px 32px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 20,
          }}
        >
          {/* Progress bar */}
          <ProgressBar
            currentTime={currentTime}
            duration={duration}
            onSeek={seekTo}
            disabled={playbackState === 'idle' || playbackState === 'loading'}
          />

          {/* Play controls */}
          <PlayControls
            playbackState={playbackState}
            onToggle={togglePlay}
            onPrev={prevSong}
            onNext={nextSong}
            disabled={playbackState === 'loading'}
          />

          {/* Volume control */}
          <VolumeControl
            volume={volume}
            isMuted={isMuted}
            onVolumeChange={changeVolume}
            onMuteToggle={toggleMuteAudio}
          />
        </div>
      </div>
    </div>
  )
}
