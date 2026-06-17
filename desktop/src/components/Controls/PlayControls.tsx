import { motion } from 'framer-motion'
import { SkipBack, Play, Pause, SkipForward } from 'lucide-react'
import type { PlaybackState } from '../../types'

interface PlayControlsProps {
  playbackState: PlaybackState
  onToggle: () => void
  onPrev: () => void
  onNext: () => void
  disabled?: boolean
}

export default function PlayControls({
  playbackState,
  onToggle,
  onPrev,
  onNext,
  disabled = false,
}: PlayControlsProps) {
  const isPlaying = playbackState === 'playing'
  const isLoading = playbackState === 'loading'

  return (
    <div className="flex items-center justify-center gap-4">
      {/* Previous */}
      <motion.button
        className="ctrl-btn"
        onClick={onPrev}
        disabled={disabled}
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.92 }}
        aria-label="上一首"
      >
        <SkipBack size={18} />
      </motion.button>

      {/* Play/Pause */}
      <motion.button
        className="ctrl-btn primary"
        onClick={onToggle}
        disabled={disabled || isLoading}
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.92 }}
        aria-label={isPlaying ? '暂停' : '播放'}
      >
        {isLoading ? (
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="8" />
            </svg>
          </motion.div>
        ) : isPlaying ? (
          <Pause size={22} />
        ) : (
          <Play size={22} style={{ marginLeft: 2 }} />
        )}
      </motion.button>

      {/* Next */}
      <motion.button
        className="ctrl-btn"
        onClick={onNext}
        disabled={disabled}
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.92 }}
        aria-label="下一首"
      >
        <SkipForward size={18} />
      </motion.button>
    </div>
  )
}
