import { useRef, useEffect } from 'react'
import { COLORS, SPEED_CONFIG } from '../../lib/constants'
import type { FluidSpeed, ShaderMood } from '../../types'

interface FluidBackgroundProps {
  speed?: FluidSpeed
  mood?: ShaderMood
}

export default function FluidBackground({
  speed = 'medium',
  mood = 'normal',
}: FluidBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const cfg = SPEED_CONFIG[speed]
  const intensity = mood === 'excited' ? 1.3 : mood === 'calm' ? 0.7 : 1.0

  // ── Canvas 2D fluid simulation ──
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationId: number
    let time = 0

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    // Blob state
    const blobs = [
      { x: 0.35, y: 0.40, r: 0.30, color: COLORS.pigment.red, phase: 0, speed: 1.0 },
      { x: 0.60, y: 0.45, r: 0.26, color: COLORS.pigment.blue, phase: 2.1, speed: 0.85 },
      { x: 0.48, y: 0.55, r: 0.24, color: COLORS.pigment.yellow, phase: 4.3, speed: 0.9 },
    ]

    const animate = () => {
      time += 0.008 * cfg.speed

      const w = canvas.width
      const h = canvas.height
      const scale = Math.min(w, h)

      // Clear to dark background
      ctx.fillStyle = COLORS.bg
      ctx.fillRect(0, 0, w, h)

      // Draw each blob on an offscreen canvas for compositing
      for (const blob of blobs) {
        // Lissajous movement
        const bx = 0.5 + Math.sin(time * blob.speed * 1.3 + blob.phase) * 0.15 + Math.cos(time * blob.speed * 0.7 + blob.phase) * 0.08
        const by = 0.5 + Math.cos(time * blob.speed * 1.1 + blob.phase) * 0.12 + Math.sin(time * blob.speed * 0.8 + blob.phase) * 0.1

        // Repulsion between blobs
        for (const other of blobs) {
          if (other === blob) continue
          const dx = bx - other.x
          const dy = by - other.y
          const dist = Math.sqrt(dx * dx + dy * dy)
          const minDist = (blob.r + other.r) * 0.85
          if (dist < minDist && dist > 0.001) {
            const force = (minDist - dist) / minDist * 0.015
            blob.x -= (dx / dist) * force
            blob.y -= (dy / dist) * force
          }
        }

        blob.x += (bx - blob.x) * 0.02
        blob.y += (by - blob.y) * 0.02

        // Radius oscillation
        const currentR = blob.r + Math.sin(time * 0.4 + blob.phase) * 0.03

        // Draw blob with multiple layers for oil-paint look
        const cx = blob.x * w
        const cy = blob.y * h
        const radius = currentR * scale

        // ── Outer glow (soft, large) ──
        const outerGlow = ctx.createRadialGradient(cx, cy, radius * 0.3, cx, cy, radius * 1.3)
        const [r, g, b] = blob.color
        outerGlow.addColorStop(0, `rgba(${Math.round(r*255)}, ${Math.round(g*255)}, ${Math.round(b*255)}, ${0.6 * intensity})`)
        outerGlow.addColorStop(0.5, `rgba(${Math.round(r*255)}, ${Math.round(g*255)}, ${Math.round(b*255)}, ${0.25 * intensity})`)
        outerGlow.addColorStop(1, `rgba(${Math.round(r*255)}, ${Math.round(g*255)}, ${Math.round(b*255)}, 0)`)

        ctx.fillStyle = outerGlow
        ctx.beginPath()
        // Organically distorted circle via multiple overlapping ellipses
        for (let a = 0; a < Math.PI * 2; a += 0.15) {
          const noise = 1 + Math.sin(a * 5 + time * 0.6 + blob.phase) * 0.08
            + Math.cos(a * 3 + time * 0.4 + blob.phase) * 0.06
            + Math.sin(a * 7 + time * 0.3) * 0.04
          const rx = cx + Math.cos(a) * radius * 1.3 * noise
          const ry = cy + Math.sin(a) * radius * 1.3 * noise
          if (a === 0) ctx.moveTo(rx, ry)
          else ctx.lineTo(rx, ry)
        }
        ctx.closePath()
        ctx.fill()

        // ── Core (dense, smaller) ──
        const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * 0.5)
        coreGrad.addColorStop(0, `rgba(${Math.round(r*255)}, ${Math.round(g*255)}, ${Math.round(b*255)}, ${0.9 * intensity})`)
        coreGrad.addColorStop(0.6, `rgba(${Math.round(r*255)}, ${Math.round(g*255)}, ${Math.round(b*255)}, ${0.5 * intensity})`)
        coreGrad.addColorStop(1, `rgba(${Math.round(r*255)}, ${Math.round(g*255)}, ${Math.round(b*255)}, 0)`)

        ctx.fillStyle = coreGrad
        ctx.beginPath()
        // Organically distorted inner blob
        for (let a = 0; a < Math.PI * 2; a += 0.12) {
          const noise = 1 + Math.sin(a * 4 + time * 0.5 + blob.phase + 1) * 0.12
            + Math.cos(a * 6 + time * 0.35 + blob.phase) * 0.07
          const rx = cx + Math.cos(a) * radius * 0.6 * noise
          const ry = cy + Math.sin(a) * radius * 0.6 * noise
          if (a === 0) ctx.moveTo(rx, ry)
          else ctx.lineTo(rx, ry)
        }
        ctx.closePath()
        ctx.fill()

        // ── Specular highlight (oil paint sheen) ──
        const hlGrad = ctx.createRadialGradient(
          cx - radius * 0.15, cy - radius * 0.2, 0,
          cx - radius * 0.1, cy - radius * 0.15, radius * 0.25
        )
        hlGrad.addColorStop(0, `rgba(255, 255, 255, ${0.15 * intensity})`)
        hlGrad.addColorStop(1, 'rgba(255, 255, 255, 0)')
        ctx.fillStyle = hlGrad
        ctx.beginPath()
        ctx.arc(cx - radius * 0.08, cy - radius * 0.12, radius * 0.22, 0, Math.PI * 2)
        ctx.fill()
      }

      // ── Film grain texture ──
      const imageData = ctx.getImageData(0, 0, w, h)
      const data = imageData.data
      for (let i = 0; i < data.length; i += 4) {
        const grain = (Math.random() - 0.5) * 6
        data[i] = Math.min(255, Math.max(0, data[i] + grain))
        data[i + 1] = Math.min(255, Math.max(0, data[i + 1] + grain))
        data[i + 2] = Math.min(255, Math.max(0, data[i + 2] + grain))
      }
      ctx.putImageData(imageData, 0, 0)

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
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }}
      />
      {/* Vignette */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'radial-gradient(ellipse at center, transparent 40%, rgba(2,2,3,0.5) 100%)',
        pointerEvents: 'none', zIndex: 2,
      }} />
    </div>
  )
}
