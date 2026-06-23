import { useRef, useEffect } from 'react'
import { SPEED_CONFIG } from '../../lib/constants'
import type { FluidSpeed } from '../../types'

interface RippleBackgroundProps {
  speed?: FluidSpeed
}

const centerRand = (range: number) => {
  const u = Math.random() + Math.random()
  return (u / 2) * range
}

const spawnDrop = (w: number, h: number, raindrops: { x: number; y: number; progress: number; spd: number }[]) => {
  const x = w * 0.15 + centerRand(w * 0.7)
  const y = h * 0.15 + centerRand(h * 0.5)
  raindrops.push({ x, y, progress: 0, spd: 0.3 + Math.random() * 0.4 })
}

export default function RippleBackground({ speed = 'medium' }: RippleBackgroundProps) {
  const bgCanvasRef = useRef<HTMLCanvasElement>(null)
  const rippleCvsRef = useRef<HTMLCanvasElement | null>(null)
  const cfg = SPEED_CONFIG[speed]

  // Create/destroy foreground ripple canvas on document.body
  useEffect(() => {
    const cvs = document.createElement('canvas')
    cvs.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:999;pointer-events:none;display:block'
    document.body.appendChild(cvs)
    rippleCvsRef.current = cvs
    return () => { cvs.remove(); rippleCvsRef.current = null }
  }, [])

  useEffect(() => {
    const canvas = bgCanvasRef.current
    const rippleCvs = rippleCvsRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const rctx = rippleCvs?.getContext('2d')
    if (!ctx) return
    let animId: number, time = 0

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
      const rc = rippleCvsRef.current
      if (rc) { rc.width = window.innerWidth; rc.height = window.innerHeight }
    }
    resize()
    window.addEventListener('resize', resize)

    const ripples: { x: number; y: number; maxR: number; r: number; alpha: number; lw: number; phase: number }[] = []
    const raindrops: { x: number; y: number; progress: number; spd: number }[] = []
    let dropTimer = 0

    // Seed 1 initial ripple
    ripples.push({
      x: canvas.width * 0.3 + centerRand(canvas.width * 0.4),
      y: canvas.height * 0.2 + centerRand(canvas.height * 0.4),
      maxR: 150 + Math.random() * 200, r: 0,
      alpha: 0.4, lw: 1.5, phase: 0,
    })

    const animate = () => {
      time += 0.008 * cfg.speed
      const w = canvas.width, h = canvas.height

      // Background gradient
      const bgGrad = ctx.createLinearGradient(0, 0, 0, h)
      bgGrad.addColorStop(0, '#0a1628')
      bgGrad.addColorStop(0.4, '#0d1f3c')
      bgGrad.addColorStop(0.7, '#0f2547')
      bgGrad.addColorStop(1, '#0a1a35')
      ctx.fillStyle = bgGrad
      ctx.fillRect(0, 0, w, h)

      // Underwater light
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

      // Moonlight
      ctx.save()
      ctx.globalAlpha = 0.06
      const mx = w * 0.7 + Math.sin(time * 0.2) * w * 0.05, my = h * 0.15
      const mg = ctx.createRadialGradient(mx, my, 0, mx, my, Math.min(w, h) * 0.6)
      mg.addColorStop(0, '#8098b0')
      mg.addColorStop(0.3, '#405060')
      mg.addColorStop(1, 'transparent')
      ctx.fillStyle = mg
      ctx.fillRect(0, 0, w, h)
      ctx.restore()

      // ── Foreground ripple layer (rctx) — renders on top of lyrics ──
      if (rctx) {
        rctx.clearRect(0, 0, w, h)

        // Spawn drops — seed immediately if nothing is active
        if (raindrops.length === 0 && ripples.length === 0) { spawnDrop(w, h, raindrops); dropTimer = 0 }
        dropTimer += 0.016
        const interval = 2.5 + Math.random() * 1.5
        if (dropTimer > interval && raindrops.length < 1) { dropTimer = 0; spawnDrop(w, h, raindrops) }

        // Falling drops
        for (let i = raindrops.length - 1; i >= 0; i--) {
          const d = raindrops[i]
          d.progress += 0.016 * d.spd * 3
          if (d.progress < 0.85) {
            const dy = -20 + (d.y + 20) * d.progress
            rctx.save()
            rctx.globalAlpha = 0.3 * (1 - d.progress)
            rctx.strokeStyle = '#c0d8f0'
            rctx.lineWidth = 1.2
            rctx.beginPath()
            rctx.moveTo(d.x, dy)
            rctx.lineTo(d.x, dy + 8)
            rctx.stroke()
            rctx.restore()
          }
          if (d.progress >= 1) {
            ripples.push({ x: d.x, y: d.y, maxR: 150 + Math.random() * 200, r: 0, alpha: 0.5, lw: 1.5, phase: 0 })
            raindrops.splice(i, 1)
          }
        }

        // Ripples — visible above lyrics glass
        for (let i = ripples.length - 1; i >= 0; i--) {
          const rp = ripples[i]
          rp.phase += 0.012
          rp.r += 0.35 * (1 - rp.phase * 0.7)
          rp.alpha -= 0.004
          if (rp.alpha <= 0 || rp.r > rp.maxR) { ripples.splice(i, 1); continue }
          rctx.save()
          rctx.globalAlpha = rp.alpha
          rctx.strokeStyle = '#a0c8e0'
          rctx.lineWidth = rp.lw * (1 - rp.phase * 0.6)
          rctx.beginPath()
          rctx.arc(rp.x, rp.y, rp.r, 0, Math.PI * 2)
          rctx.stroke()
          if (rp.r > 8) {
            rctx.globalAlpha = rp.alpha * 0.4
            rctx.lineWidth = rp.lw * 0.6
            rctx.beginPath()
            rctx.arc(rp.x, rp.y, rp.r * 0.55, 0, Math.PI * 2)
            rctx.stroke()
          }
          rctx.restore()
        }
      }

      // Vignette
      const vg = ctx.createRadialGradient(w * 0.5, h * 0.5, Math.min(w, h) * 0.3, w * 0.5, h * 0.5, Math.max(w, h) * 0.75)
      vg.addColorStop(0, 'transparent')
      vg.addColorStop(1, 'rgba(0,0,0,0.35)')
      ctx.fillStyle = vg
      ctx.fillRect(0, 0, w, h)

      animId = requestAnimationFrame(animate)
    }
    animate()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [cfg.speed])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 0, background: '#0a1628', overflow: 'hidden' }}>
      <canvas ref={bgCanvasRef} style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }} />
    </div>
  )
}
