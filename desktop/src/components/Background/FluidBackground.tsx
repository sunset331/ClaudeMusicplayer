import { useRef, useEffect } from 'react'
import { COLORS, SPEED_CONFIG } from '../../lib/constants'
import type { FluidSpeed, ShaderMood, DisplayMode } from '../../types'

interface FluidBackgroundProps {
  speed?: FluidSpeed; mood?: ShaderMood; displayMode?: DisplayMode
}

const rgb = (c: readonly number[], a: number) =>
  `rgba(${c.map(v => Math.round(v * 255)).join(',')}, ${a})`

function noise(x: number, y: number, seed: number): number {
  const n = Math.sin(x * 12.9898 + y * 78.233 + seed) * 43758.5453
  return n - Math.floor(n)
}
function fbm(x: number, y: number, t: number, seed: number): number {
  let v = 0, a = 0.5, f = 1.0
  for (let i = 0; i < 3; i++) { v += a * noise(x * f + t * 0.3, y * f, seed + i); a *= 0.5; f *= 2.0 }
  return v
}

export default function FluidBackground({ speed = 'medium', mood = 'normal', displayMode = 'pigment' }: FluidBackgroundProps) {
  const bgCanvasRef = useRef<HTMLCanvasElement>(null)
  const rippleCvsRef = useRef<HTMLCanvasElement | null>(null)
  const cfg = SPEED_CONFIG[speed]
  const intensity = mood === 'excited' ? 1.3 : mood === 'calm' ? 0.7 : 1.0
  const modeRef = useRef(displayMode)
  modeRef.current = displayMode

  // Create/destroy ripple canvas directly on document.body
  useEffect(() => {
    const cvs = document.createElement('canvas')
    cvs.style.cssText = 'position:fixed;inset:0;width:100%;height:100%;z-index:999;pointer-events:none;display:none'
    document.body.appendChild(cvs)
    rippleCvsRef.current = cvs
    return () => { cvs.remove(); rippleCvsRef.current = null }
  }, [])

  useEffect(() => {
    const cvs = rippleCvsRef.current
    if (cvs) {
      cvs.style.display = displayMode === 'soft' ? 'block' : 'none'
      if (displayMode === 'soft') {
        cvs.width = window.innerWidth; cvs.height = window.innerHeight
      }
    }
  }, [displayMode])

  useEffect(() => {
    const canvas = bgCanvasRef.current
    const rippleCvs = rippleCvsRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    const rctx = rippleCvs?.getContext('2d')
    if (!ctx) return
    let animId: number, time = 0

    const resize = () => {
      canvas.width = window.innerWidth; canvas.height = window.innerHeight
      const rc = rippleCvsRef.current
      if (rc) { rc.width = window.innerWidth; rc.height = window.innerHeight }
    }
    resize(); window.addEventListener('resize', resize)

    // ── Pigment state ──
    const pigments = [
      { cx: 0.35, cy: 0.42, color: COLORS.pigment.red,   seed: 0,   drops: 5, scale: 0.32 },
      { cx: 0.62, cy: 0.48, color: COLORS.pigment.blue,  seed: 100, drops: 4, scale: 0.28 },
      { cx: 0.48, cy: 0.58, color: COLORS.pigment.yellow, seed: 200, drops: 4, scale: 0.26 },
    ]
    // ── Ripple state ──
    const ripples: { x: number; y: number; maxR: number; r: number; alpha: number; lw: number; phase: number }[] = []
    const raindrops: { x: number; y: number; progress: number; spd: number }[] = []
    let dropTimer = 0
    // Center-biased random: higher probability near center
    const centerRand = (range: number) => {
      const u = Math.random() + Math.random() // triangular distribution, peaks at center
      return (u / 2) * range
    }
    const spawnDrop = (w: number, h: number) => {
      const x = w * 0.15 + centerRand(w * 0.7)  // bias toward horizontal center
      const y = h * 0.15 + centerRand(h * 0.5)  // bias toward upper-center
      raindrops.push({ x, y, progress: 0, spd: 0.3 + Math.random() * 0.4 })
    }
    // Seed 1 initial ripple (not 6)
    ripples.push({
      x: canvas.width * 0.3 + centerRand(canvas.width * 0.4),
      y: canvas.height * 0.2 + centerRand(canvas.height * 0.4),
      maxR: 150 + Math.random() * 200, r: 0,
      alpha: 0.4, lw: 1.5, phase: 0,
    })

    const animate = () => {
      time += 0.008 * cfg.speed
      const w = canvas.width, h = canvas.height
      const m = modeRef.current

      if (m === 'soft') {
        // ══════ Ripple mode ══════
        const bgGrad = ctx.createLinearGradient(0, 0, 0, h)
        bgGrad.addColorStop(0, '#0a1628'); bgGrad.addColorStop(0.4, '#0d1f3c')
        bgGrad.addColorStop(0.7, '#0f2547'); bgGrad.addColorStop(1, '#0a1a35')
        ctx.fillStyle = bgGrad; ctx.fillRect(0, 0, w, h)

        // Underwater light
        ctx.save(); ctx.globalAlpha = 0.03
        for (let i = 0; i < 3; i++) {
          const cx = w * 0.3 + Math.sin(time * 0.4 + i * 2.1) * w * 0.25
          const cy = h * 0.4 + Math.cos(time * 0.35 + i * 1.7) * h * 0.2
          const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.min(w, h) * 0.35)
          grd.addColorStop(0, '#3a6080'); grd.addColorStop(1, 'transparent')
          ctx.fillStyle = grd; ctx.fillRect(0, 0, w, h)
        }
        ctx.restore()

        // Moonlight
        ctx.save(); ctx.globalAlpha = 0.06
        const mx = w * 0.7 + Math.sin(time * 0.2) * w * 0.05, my = h * 0.15
        const mg = ctx.createRadialGradient(mx, my, 0, mx, my, Math.min(w, h) * 0.6)
        mg.addColorStop(0, '#8098b0'); mg.addColorStop(0.3, '#405060'); mg.addColorStop(1, 'transparent')
        ctx.fillStyle = mg; ctx.fillRect(0, 0, w, h); ctx.restore()

        // ── Foreground ripple layer (rctx) — renders on top of lyrics ──
        if (rctx) {
          rctx.clearRect(0, 0, w, h)

          // Spawn drops — seed immediately if nothing is active
          if (raindrops.length === 0 && ripples.length === 0) { spawnDrop(w, h); dropTimer = 0 }
          dropTimer += 0.016; const interval = 2.5 + Math.random() * 1.5
          if (dropTimer > interval && raindrops.length < 1) { dropTimer = 0; spawnDrop(w, h) }

          // Falling drops
          for (let i = raindrops.length - 1; i >= 0; i--) {
            const d = raindrops[i]; d.progress += 0.016 * d.spd * 3
            if (d.progress < 0.85) {
              const dy = -20 + (d.y + 20) * d.progress
              rctx.save(); rctx.globalAlpha = 0.3 * (1 - d.progress); rctx.strokeStyle = '#c0d8f0'; rctx.lineWidth = 1.2
              rctx.beginPath(); rctx.moveTo(d.x, dy); rctx.lineTo(d.x, dy + 8); rctx.stroke(); rctx.restore()
            }
            if (d.progress >= 1) {
              ripples.push({ x: d.x, y: d.y, maxR: 150 + Math.random() * 200, r: 0, alpha: 0.5, lw: 1.5, phase: 0 })
              raindrops.splice(i, 1)
            }
          }

          // Ripples — visible above lyrics glass
          for (let i = ripples.length - 1; i >= 0; i--) {
            const rp = ripples[i]; rp.phase += 0.012; rp.r += 0.35 * (1 - rp.phase * 0.7); rp.alpha -= 0.004
            if (rp.alpha <= 0 || rp.r > rp.maxR) { ripples.splice(i, 1); continue }
            rctx.save(); rctx.globalAlpha = rp.alpha; rctx.strokeStyle = '#a0c8e0'; rctx.lineWidth = rp.lw * (1 - rp.phase * 0.6)
            rctx.beginPath(); rctx.arc(rp.x, rp.y, rp.r, 0, Math.PI * 2); rctx.stroke()
            if (rp.r > 8) { rctx.globalAlpha = rp.alpha * 0.4; rctx.lineWidth = rp.lw * 0.6; rctx.beginPath(); rctx.arc(rp.x, rp.y, rp.r * 0.55, 0, Math.PI * 2); rctx.stroke() }
            rctx.restore()
          }
        }

        // Vignette
        const vg = ctx.createRadialGradient(w * 0.5, h * 0.5, Math.min(w, h) * 0.3, w * 0.5, h * 0.5, Math.max(w, h) * 0.75)
        vg.addColorStop(0, 'transparent'); vg.addColorStop(1, 'rgba(0,0,0,0.35)')
        ctx.fillStyle = vg; ctx.fillRect(0, 0, w, h)

      } else {
        // ══════ Pigment mode ══════
        const scale = Math.min(w, h)
        ctx.fillStyle = COLORS.bg; ctx.fillRect(0, 0, w, h)

        // Repulsion
        for (const p of pigments) {
          for (const q of pigments) {
            if (p === q) continue
            const dx = p.cx - q.cx, dy = p.cy - q.cy, dist = Math.sqrt(dx * dx + dy * dy)
            const minDist = (p.scale + q.scale) * 0.7
            if (dist < minDist && dist > 0.001) { const f = (minDist - dist) / minDist * 0.008; p.cx += (dx / dist) * f; p.cy += (dy / dist) * f; q.cx -= (dx / dist) * f; q.cy -= (dy / dist) * f }
          }
        }

        for (const p of pigments) {
          const s = p.seed * 0.01
          p.cx += (0.5 + Math.sin(time * 0.4 + s) * 0.12 + Math.cos(time * 0.3 + s * 2) * 0.08 - p.cx) * 0.015
          p.cy += (0.5 + Math.cos(time * 0.35 + s) * 0.10 + Math.sin(time * 0.28 + s * 1.5) * 0.09 - p.cy) * 0.015
          const px = p.cx * w, py = p.cy * h, baseR = p.scale * scale

          for (let d = 0; d < p.drops; d++) {
            const da = (d / p.drops) * Math.PI * 2 + time * 0.15
            const dd = baseR * 0.25 * (0.5 + 0.5 * Math.sin(time * 0.2 + d))
            const dx = px + Math.cos(da) * dd, dy = py + Math.sin(da) * dd
            const dropR = baseR * (0.5 + 0.3 * Math.sin(time * 0.25 + d * 1.7))
            ctx.save(); ctx.filter = `blur(${baseR * 0.18}px)`; ctx.fillStyle = rgb(p.color, 0.5 * intensity)
            ctx.beginPath()
            for (let i = 0; i <= 32; i++) {
              const a = (i / 32) * Math.PI * 2
              const def = 1 + fbm(Math.cos(a) * 3 + d, Math.sin(a) * 3 + d, time * 0.4, p.seed) * 0.35
              const rx = dx + Math.cos(a) * dropR * def, ry = dy + Math.sin(a) * dropR * def
              i === 0 ? ctx.moveTo(rx, ry) : ctx.lineTo(rx, ry)
            }
            ctx.closePath(); ctx.fill(); ctx.restore()
          }
          // Core
          ctx.save(); ctx.filter = `blur(${baseR * 0.08}px)`; ctx.fillStyle = rgb(p.color, 0.7 * intensity); ctx.beginPath()
          for (let i = 0; i <= 24; i++) {
            const a = (i / 24) * Math.PI * 2
            const def = 1 + fbm(Math.cos(a) * 2.5, Math.sin(a) * 2.5, time * 0.35, p.seed + 50) * 0.25
            const rx = px + Math.cos(a) * baseR * 0.45 * def, ry = py + Math.sin(a) * baseR * 0.45 * def
            i === 0 ? ctx.moveTo(rx, ry) : ctx.lineTo(rx, ry)
          }
          ctx.closePath(); ctx.fill(); ctx.restore()

          // Tendrils
          ctx.save(); ctx.filter = `blur(${baseR * 0.12}px)`
          for (let t = 0; t < 3; t++) {
            const ta = (t / 3) * Math.PI * 2 + time * 0.12 + p.seed
            const tl = baseR * (0.8 + 0.4 * Math.sin(time * 0.3 + t))
            ctx.strokeStyle = rgb(p.color, 0.3 * intensity); ctx.lineWidth = baseR * 0.12; ctx.lineCap = 'round'; ctx.beginPath()
            ctx.moveTo(px, py)
            const cp1x = px + Math.cos(ta) * tl * 0.5 + Math.sin(ta) * baseR * 0.15
            const cp1y = py + Math.sin(ta) * tl * 0.5 + Math.cos(ta) * baseR * 0.15
            const cp2x = px + Math.cos(ta) * tl * 0.8 + Math.sin(ta + 0.5) * baseR * 0.1
            const cp2y = py + Math.sin(ta) * tl * 0.8 + Math.cos(ta + 0.5) * baseR * 0.1
            ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, px + Math.cos(ta) * tl, py + Math.sin(ta) * tl); ctx.stroke()
          }
          ctx.restore()
          // Highlight
          ctx.fillStyle = `rgba(255,255,255,${0.08 * intensity})`; ctx.beginPath()
          ctx.ellipse(px - baseR * 0.1, py - baseR * 0.15, baseR * 0.15, baseR * 0.08, -0.3, 0, Math.PI * 2); ctx.fill()
        }
      }
      animId = requestAnimationFrame(animate)
    }
    animate()
    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize) }
  }, [cfg.speed, intensity])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 0, background: displayMode === 'soft' ? '#0a1628' : COLORS.bg, overflow: 'hidden' }}>
      <canvas ref={bgCanvasRef} style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }} />
      {displayMode === 'pigment' && (
        <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 2,
          background: 'radial-gradient(ellipse at center, transparent 40%, rgba(2,2,3,0.5) 100%)' }} />
      )}
    </div>
  )
}
