import { AnimatePresence, motion } from 'motion/react'

import type { Effect, Flight } from '../../lib/reducer'
import { BANK, type SeatGeometry } from './layout'

interface Props {
  geometry: Record<string, SeatGeometry>
  flights: Flight[]
  effects: Effect[]
}

function lightning(a: { x: number; y: number }, b: { x: number; y: number }): string {
  const steps = 7
  const pts: string[] = []
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const jitter = i === 0 || i === steps ? 0 : (i % 2 ? 2.4 : -2.4)
    const dx = b.y - a.y
    const dy = a.x - b.x
    const len = Math.hypot(dx, dy) || 1
    pts.push(`${a.x + (b.x - a.x) * t + (dx / len) * jitter},${a.y + (b.y - a.y) * t + (dy / len) * jitter}`)
  }
  return `M ${pts.join(' L ')}`
}

export function TableFx({ geometry, flights, effects }: Props) {
  const anchor = (id: string | null) => (id && geometry[id] ? geometry[id].anchor : BANK)

  return (
    <>
      <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="0.8" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <AnimatePresence>
          {effects.map((fx) => {
            if (fx.kind === 'alliance') {
              const [a, b] = fx.players.map(anchor)
              return (
                <motion.line key={fx.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                  stroke="var(--color-lime)" strokeWidth={3} vectorEffect="non-scaling-stroke" strokeLinecap="round"
                  strokeDasharray="6 6" filter="url(#glow)"
                  initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: [0, 1, 0.75] }}
                  exit={{ opacity: 0 }} transition={{ duration: 1.1 }} />
              )
            }
            if (fx.kind === 'betrayal') {
              const [a, b] = fx.players.map(anchor)
              return (
                <motion.path key={fx.id} d={lightning(a, b)} fill="none" stroke="var(--color-pink)" strokeWidth={4}
                  vectorEffect="non-scaling-stroke" strokeLinejoin="bevel" filter="url(#glow)"
                  initial={{ pathLength: 0, opacity: 1 }} animate={{ pathLength: 1, opacity: [1, 0.3, 1, 0.3, 0.9] }}
                  exit={{ opacity: 0 }} transition={{ duration: 1.4 }} />
              )
            }
            if (fx.kind === 'gang') {
              const [victim, ...takers] = fx.players
              const v = anchor(victim)
              return (
                <motion.g key={fx.id} initial={{ opacity: 0 }} animate={{ opacity: 0.85 }} exit={{ opacity: 0 }}>
                  {takers.map((t) => {
                    const a = anchor(t)
                    return <line key={t} x1={a.x} y1={a.y} x2={v.x} y2={v.y} stroke="var(--color-amber)"
                      strokeWidth={2} strokeDasharray="2 4" vectorEffect="non-scaling-stroke" />
                  })}
                </motion.g>
              )
            }
            return null
          })}
        </AnimatePresence>
      </svg>

      {/* coins in flight */}
      <AnimatePresence>
        {flights.map((f, i) => {
          const from = anchor(f.from)
          const to = anchor(f.to)
          const bonus = f.kind.endsWith('bonus')
          return (
            <motion.div
              key={f.id}
              className="pointer-events-none absolute z-30 -mt-3 -ml-3 grid h-6 w-6 place-items-center rounded-full border-2 font-mono text-[10px] font-bold"
              style={{
                background: bonus ? 'var(--color-lime)' : 'var(--color-gold)',
                borderColor: bonus ? '#e9ffb3' : '#fff2b8',
                color: 'var(--color-ink)',
                boxShadow: `0 0 16px ${bonus ? 'var(--color-lime)' : 'var(--color-gold)'}`,
              }}
              initial={{ left: `${from.x}%`, top: `${from.y}%`, scale: 0.3, opacity: 0 }}
              animate={{ left: `${to.x}%`, top: `${to.y}%`, scale: [0.3, 1.3, 1], opacity: [0, 1, 1, 0], rotateY: 720 }}
              transition={{ duration: 1.3, delay: i * 0.18, ease: 'easeInOut' }}
              aria-hidden
            >
              {bonus ? '+' : '¢'}
            </motion.div>
          )
        })}
      </AnimatePresence>

      {/* liar markers */}
      <AnimatePresence>
        {effects.filter((fx) => fx.kind === 'lie').map((fx) => {
          const at = geometry[fx.players[0]]?.seat
          if (!at) return null
          return (
            <motion.div key={fx.id} className="pointer-events-none absolute z-30 text-3xl"
              style={{ left: `${at.x}%`, top: `${at.y - 11}%`, x: '-50%' }}
              initial={{ opacity: 0, y: 10, scale: 0.5 }} animate={{ opacity: [0, 1, 1, 0], y: -20, scale: 1.2 }}
              transition={{ duration: 2.4 }} aria-hidden>
              🤥
            </motion.div>
          )
        })}
      </AnimatePresence>
    </>
  )
}
