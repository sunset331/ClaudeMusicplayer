import { useRef, useEffect } from 'react'
import type { FluidSpeed, ShaderMood } from '../../types'

interface SoftBackgroundProps { speed?: FluidSpeed; mood?: ShaderMood }

interface Ripple {
  x: number; y: number
  maxR: number; r: number; alpha: number
  lineWidth: number; phase: number
}

interface Raindrop {
  x: number; y: number
  progress: number  // 0→1 falling
  speed: number
}

export default function SoftBackground({ speed = 'medium' }: SoftBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const speedMul = speed === 'slow' ? 0.5 : speed === 'fast' ? 2.0 : 1.0

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let animId: number
    let time = 0

    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight }
    resize(); window.addEventListener('resize', resize)

    const ripples: Ripple[] = []
    const raindrops: Raindrop[] = []

    // Spawn raindrops periodically
    let dropTimer = 0
    const spawnDrop = () => {
      const w = canvas.width
      const targetY = Math.random() * canvas.height * 0.7 + canvas.height * 0.1
      raindrops.push({
        x: Math.random() * w,
        y: targetY,  // where the drop will hit (stored in y)
        progress: 0,
        speed: 0.4 + Math.random() * 0.6,
      })
    }

    const animate = () => {
      const dt = 0.016 // cap delta
      time += dt * speedMul
      const w = canvas.width, h = canvas.height

      // ── Deep lake gradient background ──
      const bgGrad = ctx.createLinearGradient(0, 0, 0, h)
      bgGrad.addColorStop(0, '#0a1628')
      bgGrad.addColorStop(0.4, '#0d1f3c')
      bgGrad.addColorStop(0.7, '#0f2547')
      bgGrad.addColorStop(1, '#0a1a35')
      ctx.fillStyle = bgGrad
      ctx.fillRect(0, 0, w, h)

      // ── Subtle underwater light caustics ──
      ctx.save()
      ctx.globalAlpha = 0.03
      for (let i = 0; i < 3; i++) {
        const cx = w * 0.3 + Math.sin(time * 0.4 + i * 2.1) * w * 0.25
        const cy = h * 0.4 + Math.cos(time * 0.35 + i * 1.7) * h * 0.2
        const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.min(w, h) * 0.35)
        grd.addColorStop(0, '#3a6080')
        grd.addColorStop(1, 'transparent')
        ctx.fillStyle = grd
        ctx.fillRect(0, 0, w, h)
      }
      ctx.restore()

      // ── Ambient light reflection (moonlight on water) ──
      ctx.save()
      ctx.globalAlpha = 0.06
      const moonX = w * 0.7 + Math.sin(time * 0.2) * w * 0.05
      const moonY = h * 0.15
      const moonGrd = ctx.createRadialGradient(moonX, moonY, 0, moonX, moonY, Math.min(w, h) * 0.6)
      moonGrd.addColorStop(0, '#8098b0')
      moonGrd.addColorStop(0.3, '#405060')
      moonGrd.addColorStop(1, 'transparent')
      ctx.fillStyle = moonGrd
      ctx.fillRect(0, 0, w, h)
      ctx.restore()

      // ── Spawn raindrops ──
      dropTimer += dt * speedMul
      const dropInterval = 0.8 / speedMul // drops per second
      if (dropTimer > dropInterval && raindrops.length < 30) {
        dropTimer = 0
        spawnDrop()
        if (raindrops.length < 15) spawnDrop() // double spawn when sparse
      }

      // ── Animate raindrops (falling) ──
      for (let i = raindrops.length - 1; i >= 0; i--) {
        const d = raindrops[i]
        d.progress += dt * d.speed * 3
        // Draw falling drop (from top toward target y)
        const startY = -20
        const dy = startY + (d.y - startY) * d.progress
        if (d.progress < 0.85) {
          ctx.save()
          ctx.globalAlpha = 0.25 * (1 - d.progress)
          ctx.strokeStyle = '#a0b8d0'
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(d.x, dy)
          ctx.lineTo(d.x, dy + 6)
          ctx.stroke()
          ctx.restore()
        }
        // Hit water → create ripple at target position
        if (d.progress >= 1) {
          ripples.push({
            x: d.x, y: d.y, maxR: 30 + Math.random() * 60,
            r: 0, alpha: 0.5, lineWidth: 1.5 + Math.random() * 1.5, phase: 0,
          })
          raindrops.splice(i, 1)
        }
      }

      // ── Animate ripples (expanding circles, fading) ──
      for (let i = ripples.length - 1; i >= 0; i--) {
        const rip = ripples[i]
        rip.phase += dt * 2.5
        rip.r += dt * 80 * (1 - rip.phase * 0.7)
        rip.alpha -= dt * 0.8
        const a = rip.alpha
        if (a <= 0 || rip.r > rip.maxR) { ripples.splice(i, 1); continue }

        // Draw ripple ring
        ctx.save()
        ctx.globalAlpha = a
        ctx.strokeStyle = '#8098b0'
        ctx.lineWidth = rip.lineWidth * (1 - rip.phase * 0.6)
        ctx.beginPath()
        ctx.arc(rip.x, rip.y, rip.r, 0, Math.PI * 2)
        ctx.stroke()

        // Secondary echo ring (smaller, dimmer)
        if (rip.r > 8) {
          ctx.globalAlpha = a * 0.4
          ctx.lineWidth = rip.lineWidth * 0.6
          ctx.beginPath()
          ctx.arc(rip.x, rip.y, rip.r * 0.55, 0, Math.PI * 2)
          ctx.stroke()
        }
        ctx.restore()
      }

      // ── Very subtle vignette ──
      const vignette = ctx.createRadialGradient(w * 0.5, h * 0.5, Math.min(w, h) * 0.3,
        w * 0.5, h * 0.5, Math.max(w, h) * 0.75)
      vignette.addColorStop(0, 'transparent')
      vignette.addColorStop(1, 'rgba(0,0,0,0.35)')
      ctx.fillStyle = vignette
      ctx.fillRect(0, 0, w, h)

      animId = requestAnimationFrame(animate)
    }

    // Seed initial drops so it's not empty
    for (let i = 0; i < 5; i++) { spawnDrop(); ripples.push({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight * 0.6 + window.innerHeight * 0.2,
      maxR: 40 + Math.random() * 80, r: 10 + Math.random() * 40,
      alpha: 0.2 + Math.random() * 0.3, lineWidth: 1 + Math.random(), phase: Math.random() * 0.5,
    })}

    animate()

    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize) }
  }, [speedMul])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 0, overflow: 'hidden' }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%' }} />
    </div>
  )
}
