import { useRef, useEffect } from 'react'
import { usePlayerStore } from '../../store/playerStore'

export default function Spectrogram() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const playbackState = usePlayerStore((s) => s.playbackState)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let animId: number

    // Connect to the first audio element found in the page
    const audio = document.querySelector('audio')
    if (!audio) return

    let audioCtx: AudioContext | null = null
    let analyser: AnalyserNode | null = null

    try {
      audioCtx = new AudioContext()
      const source = audioCtx.createMediaElementSource(audio)
      analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.7
      source.connect(analyser)
      analyser.connect(audioCtx.destination)
    } catch {
      return // Already connected or cross-origin
    }

    const bufferLength = analyser.frequencyBinCount
    const dataArray = new Uint8Array(bufferLength)

    const draw = () => {
      animId = requestAnimationFrame(draw)
      if (!analyser) return
      analyser.getByteFrequencyData(dataArray)

      const w = canvas.width, h = canvas.height
      ctx.clearRect(0, 0, w, h)

      const barWidth = (w / bufferLength) * 2.5
      const gap = 1
      let x = 0

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * h * 0.8
        const hue = 260 + (i / bufferLength) * 60 // purple to pink gradient
        ctx.fillStyle = `hsla(${hue}, 60%, 65%, ${0.3 + (dataArray[i] / 255) * 0.5})`
        ctx.fillRect(x, h - barHeight, barWidth - gap, barHeight)
        x += barWidth
      }
    }
    draw()

    return () => {
      cancelAnimationFrame(animId)
      if (audioCtx) audioCtx.close()
    }
  }, [playbackState])

  if (playbackState !== 'playing') return null

  return (
    <canvas
      ref={canvasRef}
      width={560}
      height={60}
      style={{
        width: '100%', maxWidth: 560, height: 48, borderRadius: 12,
        opacity: 0.5, margin: '0 auto',
      }}
    />
  )
}
