import { useRef, useCallback, type MouseEvent } from 'react'
import { motion } from 'framer-motion'
import { formatTime } from '../../lib/utils'

interface ProgressBarProps {
  currentTime: number
  duration: number
  onSeek: (time: number) => void
  disabled?: boolean
}

export default function ProgressBar({
  currentTime,
  duration,
  onSeek,
  disabled = false,
}: ProgressBarProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  const handleSeek = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (disabled || !trackRef.current || duration <= 0) return
      const rect = trackRef.current.getBoundingClientRect()
      const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
      const fraction = x / rect.width
      onSeek(fraction * duration)
    },
    [disabled, duration, onSeek]
  )

  return (
    <div className="flex items-center gap-3 w-full" style={{ maxWidth: 560, margin: '0 auto' }}>
      <span className="text-time" style={{ minWidth: 40, textAlign: 'right' }}>
        {formatTime(currentTime)}
      </span>

      <div
        ref={trackRef}
        className="progress-track"
        style={{ flex: 1 }}
        onClick={handleSeek}
      >
        <motion.div
          className="progress-fill"
          style={{ width: `${progress}%` }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.1, ease: 'linear' }}
        />
      </div>

      <span className="text-time" style={{ minWidth: 40 }}>
        {formatTime(duration)}
      </span>
    </div>
  )
}
