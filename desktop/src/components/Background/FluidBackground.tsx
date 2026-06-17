import { useRef, useMemo } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { COLORS, SPEED_CONFIG } from '../../lib/constants'
import type { FluidSpeed, ShaderMood } from '../../types'

// ── GLSL Shaders ──────────────────────────────────────────────

const VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`

const FRAGMENT = /* glsl */ `
  varying vec2 vUv;
  uniform float uTime;
  uniform vec2 uResolution;
  uniform float uSpeed;
  uniform vec3 uRedPos;
  uniform vec3 uBluePos;
  uniform vec3 uYellowPos;
  uniform float uRedRadius;
  uniform float uBlueRadius;
  uniform float uYellowRadius;
  uniform float uIntensity;

  // ── Simplex 2D noise (Ashima Arts) ──
  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec3 permute(vec3 x) { return mod289(((x*34.0)+1.0)*x); }

  float snoise(vec2 v) {
    const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
    vec2 i  = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod289(i);
    vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
    vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
    m = m*m; m = m*m;
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0*a0 + h*h);
    vec3 g;
    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
  }

  // ── Blob density at pixel uv (organic metaball with noise distortion) ──
  float blobDensity(vec2 uv, vec2 center, float radius, float timeOff, float noiseScale) {
    float nx = snoise(vec2(uv.x * noiseScale + timeOff, uv.y * noiseScale));
    float ny = snoise(vec2(uv.y * noiseScale - timeOff * 0.7, uv.x * noiseScale + 1.7));
    vec2 distorted = uv - center;
    distorted.x += nx * 0.06;
    distorted.y += ny * 0.06;
    float dist = length(distorted);
    // Smooth metaball falloff
    return 1.0 - smoothstep(radius * 0.25, radius, dist);
  }

  void main() {
    vec2 uv = vUv;
    float aspect = uResolution.x / uResolution.y;
    vec2 centeredUV = (uv - 0.5) * vec2(aspect, 1.0) + 0.5;

    float speed = uSpeed * 0.4;

    // ── Compute density for each pigment ──
    float redD = blobDensity(centeredUV, uRedPos.xy, uRedRadius, uTime * speed + uRedPos.z, 3.5);
    float blueD = blobDensity(centeredUV, uBluePos.xy, uBlueRadius, uTime * speed + uBluePos.z, 3.2);
    float yellowD = blobDensity(centeredUV, uYellowPos.xy, uYellowRadius, uTime * speed + uYellowPos.z, 3.8);

    vec3 red = uRedPos;     // actual RGB pigment colors
    vec3 blue = uBluePos;
    vec3 yellow = uYellowPos;

    // ── KEY: Use dither-based layering to prevent color mixing ──
    // Each pixel belongs to the "topmost" pigment at that position.
    // In overlapping regions, use noise-based dither pattern to show
    // individual pigment dots rather than blended secondary colors.

    float dither = snoise(uv * 200.0 + uTime * 0.05) * 0.5 + 0.5; // 0..1 dither signal

    // Determine which pigment surfaces are present at this pixel
    float threshold = 0.15;
    bool hasRed = redD > threshold;
    bool hasBlue = blueD > threshold;
    bool hasYellow = yellowD > threshold;

    vec3 pigment = vec3(0.008, 0.008, 0.012); // deep abyss bg
    float maxD = 0.0;

    // Depth-sort: pick dominant pigment. In overlap zones, dither decides.
    if (hasRed && hasBlue && hasYellow) {
      // Triple overlap — dither between all three
      if (dither < 0.33) { maxD = redD; pigment = red; }
      else if (dither < 0.66) { maxD = blueD; pigment = blue; }
      else { maxD = yellowD; pigment = yellow; }
    } else if (hasRed && hasBlue) {
      if (dither < 0.5) { maxD = redD; pigment = red; }
      else { maxD = blueD; pigment = blue; }
    } else if (hasRed && hasYellow) {
      if (dither < 0.5) { maxD = redD; pigment = red; }
      else { maxD = yellowD; pigment = yellow; }
    } else if (hasBlue && hasYellow) {
      if (dither < 0.5) { maxD = blueD; pigment = blue; }
      else { maxD = yellowD; pigment = yellow; }
    } else if (hasRed) {
      maxD = redD; pigment = red;
    } else if (hasBlue) {
      maxD = blueD; pigment = blue;
    } else if (hasYellow) {
      maxD = yellowD; pigment = yellow;
    }

    vec3 bg = vec3(0.008, 0.008, 0.012);

    // Soft edge glow
    float edgeGlow = (1.0 - abs(maxD - 0.5) * 2.0) * 0.12;

    vec3 color = mix(bg, pigment, maxD * uIntensity);
    color += pigment * edgeGlow;

    // Subtle film grain
    float grain = snoise(uv * 500.0 + uTime * 0.1) * 0.012;
    color += grain;

    gl_FragColor = vec4(color, 1.0);
  }
`

// ── Fluid Plane ───────────────────────────────────────────────

function FluidPlane({
  speed,
  mood,
}: {
  speed: FluidSpeed
  mood: ShaderMood
}) {
  const meshRef = useRef<THREE.Mesh>(null)
  const { size } = useThree()

  const config = SPEED_CONFIG[speed]

  // Shader uniforms
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uResolution: { value: new THREE.Vector2(size.width, size.height) },
      uSpeed: { value: config.speed },
      uRedPos: { value: new THREE.Vector3(0.35, 0.45, 0.0) },
      uBluePos: { value: new THREE.Vector3(0.65, 0.55, 2.0) },
      uYellowPos: { value: new THREE.Vector3(0.50, 0.35, 4.0) },
      uRedRadius: { value: 0.28 },
      uBlueRadius: { value: 0.24 },
      uYellowRadius: { value: 0.22 },
      uIntensity: { value: 1.0 },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  )

  // Update speed uniform when speed changes
  uniforms.uSpeed.value = config.speed

  // Update intensity based on mood
  const targetIntensity = mood === 'excited' ? 1.3 : mood === 'calm' ? 0.7 : 1.0

  useFrame((_state, delta) => {
    uniforms.uTime.value += delta
    uniforms.uResolution.value.set(size.width, size.height)

    // Smooth intensity transition
    uniforms.uIntensity.value +=
      (targetIntensity - uniforms.uIntensity.value) * delta * 0.5

    // ── Animate blob positions (Lissajous orbits, very slow) ──
    const t = uniforms.uTime.value * config.blobMoveScale

    // Red blob — gentle figure-8
    uniforms.uRedPos.value.x = 0.35 + Math.sin(t * 1.3) * 0.12
    uniforms.uRedPos.value.y = 0.45 + Math.cos(t * 1.7) * 0.10

    // Blue blob — slower diagonal drift
    uniforms.uBluePos.value.x = 0.65 + Math.cos(t * 0.9 + 1.5) * 0.15
    uniforms.uBluePos.value.y = 0.55 + Math.sin(t * 1.1 + 0.8) * 0.13

    // Yellow blob — gentle circle
    uniforms.uYellowPos.value.x = 0.50 + Math.cos(t * 1.5 + 3.0) * 0.10
    uniforms.uYellowPos.value.y = 0.35 + Math.sin(t * 1.9 + 1.2) * 0.08

    // ── Collision avoidance: push blobs apart when edges approach ──
    const repel = (a: THREE.Vector3, b: THREE.Vector3, rA: number, rB: number) => {
      const dx = a.x - b.x
      const dy = a.y - b.y
      const dist = Math.sqrt(dx * dx + dy * dy)
      const minDist = (rA + rB) * 0.9
      if (dist < minDist && dist > 0.001) {
        const force = (minDist - dist) / minDist * 0.003
        const nx = dx / dist
        const ny = dy / dist
        a.x += nx * force
        a.y += ny * force
        b.x -= nx * force
        b.y -= ny * force
      }
    }

    repel(uniforms.uRedPos.value, uniforms.uBluePos.value, 0.28, 0.24)
    repel(uniforms.uRedPos.value, uniforms.uYellowPos.value, 0.28, 0.22)
    repel(uniforms.uBluePos.value, uniforms.uYellowPos.value, 0.24, 0.22)

    // Slow radius oscillation
    uniforms.uRedRadius.value = 0.28 + Math.sin(t * 0.3) * 0.03
    uniforms.uBlueRadius.value = 0.24 + Math.cos(t * 0.4 + 1.0) * 0.03
    uniforms.uYellowRadius.value = 0.22 + Math.sin(t * 0.35 + 2.0) * 0.02
  })

  return (
    <mesh ref={meshRef}>
      <planeGeometry args={[2, 2]} />
      <shaderMaterial
        vertexShader={VERTEX}
        fragmentShader={FRAGMENT}
        uniforms={uniforms}
        depthTest={false}
        depthWrite={false}
      />
    </mesh>
  )
}

// ── Public component ──────────────────────────────────────────

interface FluidBackgroundProps {
  speed?: FluidSpeed
  mood?: ShaderMood
}

export default function FluidBackground({
  speed = 'medium',
  mood = 'normal',
}: FluidBackgroundProps) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        background: COLORS.bg,
      }}
    >
      <Canvas
        dpr={[1, 1.5]}
        gl={{
          antialias: false,
          alpha: false,
          powerPreference: 'high-performance',
        }}
        style={{ width: '100%', height: '100%' }}
      >
        <FluidPlane speed={speed} mood={mood} />
      </Canvas>
    </div>
  )
}
