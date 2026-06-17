import { useRef, useEffect } from 'react'
import { COLORS, SPEED_CONFIG } from '../../lib/constants'
import type { FluidSpeed, ShaderMood } from '../../types'

interface FluidBackgroundProps {
  speed?: FluidSpeed
  mood?: ShaderMood
}

const rgb = (color: readonly number[], alpha: number) =>
  `rgba(${color.map(c => Math.round(c * 255)).join(',')}, ${alpha})`

const noiseDistort = (a: number, time: number, phase: number) =>
  1 + Math.sin(a * 5 + time * 0.6 + phase) * 0.08
    + Math.cos(a * 3 + time * 0.4 + phase) * 0.06
    + Math.sin(a * 7 + time * 0.3) * 0.04

const noiseDistortInner = (a: number, time: number, phase: number) =>
  1 + Math.sin(a * 4 + time * 0.5 + phase + 1) * 0.12
    + Math.cos(a * 6 + time * 0.35 + phase) * 0.07

export default function FluidBackground({
  speed = 'medium',
  mood = 'normal',
}: FluidBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const cfg = SPEED_CONFIG[speed]
  const intensity = mood === 'excited' ? 1.3 : mood === 'calm' ? 0.7 : 1.0

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let animationId: number
    let time = 0

    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight }
    resize()
    window.addEventListener('resize', resize)

    const blobs = [
      { x: 0.35, y: 0.40, r: 0.30, color: COLORS.pigment.red, phase: 0, spd: 1.0 },
      { x: 0.60, y: 0.45, r: 0.26, color: COLORS.pigment.blue, phase: 2.1, spd: 0.85 },
      { x: 0.48, y: 0.55, r: 0.24, color: COLORS.pigment.yellow, phase: 4.3, spd: 0.9 },
    ]

    const animate = () => {
      time += 0.008 * cfg.speed
      const w = canvas.width
      const h = canvas.height
      const scale = Math.min(w, h)
      ctx.fillStyle = COLORS.bg
      ctx.fillRect(0, 0, w, h)

      for (const blob of blobs) {
        // Target position — Lissajous orbit
        const tx = 0.5 + Math.sin(time * blob.spd * 1.3 + blob.phase) * 0.15
          + Math.cos(time * blob.spd * 0.7 + blob.phase) * 0.08
        const ty = 0.5 + Math.cos(time * blob.spd * 1.1 + blob.phase) * 0.12
          + Math.sin(time * blob.spd * 0.8 + blob.phase) * 0.1

        // Repulsion
        for (const other of blobs) {
          if (other === blob) continue
          const dx = tx - other.x, dy = ty - other.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          const minDist = (blob.r + other.r) * 0.85
          if (dist < minDist && dist > 0.001) {
            const f = (minDist - dist) / minDist * 0.015
            blob.x -= (dx / dist) * f; blob.y -= (dy / dist) * f
          }
        }
        blob.x += (tx - blob.x) * 0.02
        blob.y += (ty - blob.y) * 0.02

        const curR = blob.r + Math.sin(time * 0.4 + blob.phase) * 0.03
        const cx = blob.x * w, cy = blob.y * h
        const radius = curR * scale

        // Outer glow — organic blob with blur (GPU-accelerated via ctx.filter)
        ctx.save()
        ctx.filter = `blur(${radius * 0.35}px)`
        ctx.fillStyle = rgb(blob.color, 0.55 * intensity)
        ctx.beginPath()
        for (let a = 0; a < Math.PI * 2; a += 0.15) {
          const n = noiseDistort(a, time, blob.phase)
          const rx = cx + Math.cos(a) * radius * 1.3 * n
          const ry = cy + Math.sin(a) * radius * 1.3 * n
          a === 0 ? ctx.moveTo(rx, ry) : ctx.lineTo(rx, ry)
        }
        ctx.closePath(); ctx.fill()
        ctx.restore()

        // Core
        ctx.save()
        ctx.filter = `blur(${radius * 0.12}px)`
        ctx.fillStyle = rgb(blob.color, 0.75 * intensity)
        ctx.beginPath()
        for (let a = 0; a < Math.PI * 2; a += 0.12) {
          const n = noiseDistortInner(a, time, blob.phase)
          const rx = cx + Math.cos(a) * radius * 0.55 * n
          const ry = cy + Math.sin(a) * radius * 0.55 * n
          a === 0 ? ctx.moveTo(rx, ry) : ctx.lineTo(rx, ry)
        }
        ctx.closePath(); ctx.fill()
        ctx.restore()

        // Highlight
        ctx.fillStyle = `rgba(255,255,255,${0.12 * intensity})`
        ctx.beginPath()
        ctx.arc(cx - radius * 0.08, cy - radius * 0.12, radius * 0.18, 0, Math.PI * 2)
        ctx.fill()
      }
      animationId = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resize)
    }
  }, [cfg.speed, intensity])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 0, background: COLORS.bg, overflow: 'hidden' }}>
      <canvas ref={canvasRef}
        style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }} />
      {/* Vignette + grain combined in one CSS overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 2,
        background: 'radial-gradient(ellipse at center, transparent 40%, rgba(2,2,3,0.5) 100%)',
      }} />
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.025, pointerEvents: 'none', zIndex: 3,
        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        backgroundRepeat: 'repeat', backgroundSize: '256px 256px',
      }} />
    </div>
  )
}
