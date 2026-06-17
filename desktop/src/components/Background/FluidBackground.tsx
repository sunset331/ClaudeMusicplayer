import { useRef, useEffect } from 'react'
import { COLORS, SPEED_CONFIG } from '../../lib/constants'
import type { FluidSpeed, ShaderMood } from '../../types'

interface FluidBackgroundProps { speed?: FluidSpeed; mood?: ShaderMood }

const rgb = (c: readonly number[], a: number) =>
  `rgba(${c.map(v => Math.round(v * 255)).join(',')}, ${a})`

// ── Simplex-like noise for liquid deformation ──
function noise(x: number, y: number, seed: number): number {
  const n = Math.sin(x * 12.9898 + y * 78.233 + seed) * 43758.5453
  return n - Math.floor(n)
}

function fbm(x: number, y: number, t: number, seed: number): number {
  let v = 0, a = 0.5, f = 1.0
  for (let i = 0; i < 3; i++) {
    v += a * noise(x * f + t * 0.3, y * f, seed + i)
    a *= 0.5; f *= 2.0
  }
  return v
}

export default function FluidBackground({ speed = 'medium', mood = 'normal' }: FluidBackgroundProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const cfg = SPEED_CONFIG[speed]
  const intensity = mood === 'excited' ? 1.3 : mood === 'calm' ? 0.7 : 1.0

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let animId: number, time = 0

    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight }
    resize(); window.addEventListener('resize', resize)

    // Three pigment masses — each drawn as multiple overlapping fluid droplets
    const pigments = [
      { cx: 0.35, cy: 0.42, color: COLORS.pigment.red,   seed: 0,   drops: 5, scale: 0.32 },
      { cx: 0.62, cy: 0.48, color: COLORS.pigment.blue,  seed: 100, drops: 4, scale: 0.28 },
      { cx: 0.48, cy: 0.58, color: COLORS.pigment.yellow, seed: 200, drops: 4, scale: 0.26 },
    ]

    const animate = () => {
      time += 0.008 * cfg.speed
      const w = canvas.width, h = canvas.height
      const scale = Math.min(w, h)

      ctx.fillStyle = COLORS.bg
      ctx.fillRect(0, 0, w, h)

      // Repulsion between pigment centers
      for (const p of pigments) {
        for (const q of pigments) {
          if (p === q) continue
          const dx = p.cx - q.cx, dy = p.cy - q.cy
          const dist = Math.sqrt(dx * dx + dy * dy)
          const minDist = (p.scale + q.scale) * 0.7
          if (dist < minDist && dist > 0.001) {
            const f = (minDist - dist) / minDist * 0.008
            p.cx += (dx / dist) * f; p.cy += (dy / dist) * f
            q.cx -= (dx / dist) * f; q.cy -= (dy / dist) * f
          }
        }
      }

      // Draw each pigment mass
      for (const p of pigments) {
        // Slow Lissajous drift
        const s = p.seed * 0.01
        const tx = 0.5 + Math.sin(time * 0.4 + s) * 0.12 + Math.cos(time * 0.3 + s * 2) * 0.08
        const ty = 0.5 + Math.cos(time * 0.35 + s) * 0.10 + Math.sin(time * 0.28 + s * 1.5) * 0.09
        p.cx += (tx - p.cx) * 0.015
        p.cy += (ty - p.cy) * 0.015

        const px = p.cx * w, py = p.cy * h
        const baseR = p.scale * scale

        // ── Draw multiple fluid droplets that merge into one organic shape ──
        for (let d = 0; d < p.drops; d++) {
          const dropAngle = (d / p.drops) * Math.PI * 2 + time * 0.15
          const dropDist = baseR * 0.25 * (0.5 + 0.5 * Math.sin(time * 0.2 + d))
          const dx = px + Math.cos(dropAngle) * dropDist
          const dy = py + Math.sin(dropAngle) * dropDist
          const dropR = baseR * (0.5 + 0.3 * Math.sin(time * 0.25 + d * 1.7))

          // Liquid blob: distorted circle via FBM noise
          ctx.save()
          ctx.filter = `blur(${baseR * 0.18}px)`
          ctx.fillStyle = rgb(p.color, 0.5 * intensity)
          ctx.beginPath()
          const steps = 32
          for (let i = 0; i <= steps; i++) {
            const a = (i / steps) * Math.PI * 2
            // FBM noise deforms the radius
            const nx = Math.cos(a), ny = Math.sin(a)
            const deformation = 1 + fbm(nx * 3 + d, ny * 3 + d, time * 0.4, p.seed) * 0.35
            const r = dropR * deformation
            const x = dx + Math.cos(a) * r
            const y = dy + Math.sin(a) * r
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
          }
          ctx.closePath(); ctx.fill()
          ctx.restore()
        }

        // ── Core: denser center ──
        ctx.save()
        ctx.filter = `blur(${baseR * 0.08}px)`
        ctx.fillStyle = rgb(p.color, 0.7 * intensity)
        ctx.beginPath()
        const steps2 = 24
        for (let i = 0; i <= steps2; i++) {
          const a = (i / steps2) * Math.PI * 2
          const deformation = 1 + fbm(Math.cos(a) * 2.5, Math.sin(a) * 2.5, time * 0.35, p.seed + 50) * 0.25
          const r = baseR * 0.45 * deformation
          const x = px + Math.cos(a) * r
          const y = py + Math.sin(a) * r
          i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
        }
        ctx.closePath(); ctx.fill()
        ctx.restore()

        // ── Tendrils: thin wispy extensions ──
        ctx.save()
        ctx.filter = `blur(${baseR * 0.12}px)`
        const numTendrils = 3
        for (let t = 0; t < numTendrils; t++) {
          const tendrilAngle = (t / numTendrils) * Math.PI * 2 + time * 0.12 + p.seed
          const tendrilLen = baseR * (0.8 + 0.4 * Math.sin(time * 0.3 + t))
          ctx.strokeStyle = rgb(p.color, 0.3 * intensity)
          ctx.lineWidth = baseR * 0.12
          ctx.lineCap = 'round'
          ctx.beginPath()
          ctx.moveTo(px, py)
          // Bezier curve for flowing tendril
          const cp1x = px + Math.cos(tendrilAngle) * tendrilLen * 0.5 + Math.sin(tendrilAngle) * baseR * 0.15
          const cp1y = py + Math.sin(tendrilAngle) * tendrilLen * 0.5 + Math.cos(tendrilAngle) * baseR * 0.15
          const cp2x = px + Math.cos(tendrilAngle) * tendrilLen * 0.8 + Math.sin(tendrilAngle + 0.5) * baseR * 0.1
          const cp2y = py + Math.sin(tendrilAngle) * tendrilLen * 0.8 + Math.cos(tendrilAngle + 0.5) * baseR * 0.1
          const ex = px + Math.cos(tendrilAngle) * tendrilLen
          const ey = py + Math.sin(tendrilAngle) * tendrilLen
          ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, ex, ey)
          ctx.stroke()
        }
        ctx.restore()

        // ── Specular highlight ──
        ctx.fillStyle = `rgba(255,255,255,${0.08 * intensity})`
        ctx.beginPath()
        ctx.ellipse(px - baseR * 0.1, py - baseR * 0.15, baseR * 0.15, baseR * 0.08, -0.3, 0, Math.PI * 2)
        ctx.fill()
      }

      animId = requestAnimationFrame(animate)
    }
    animate()

    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize) }
  }, [cfg.speed, intensity])

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 0, background: COLORS.bg, overflow: 'hidden' }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%', position: 'absolute', inset: 0 }} />
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 2,
        background: 'radial-gradient(ellipse at center, transparent 40%, rgba(2,2,3,0.5) 100%)' }} />
    </div>
  )
}
