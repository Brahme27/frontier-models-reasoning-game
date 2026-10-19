import { AnimatePresence, motion } from 'motion/react'

import { FACES, mouthPath } from '../lib/moods'
import type { Mood } from '../lib/types'

interface FaceProps {
  mood: Mood
  color: string
  size?: number
  dimmed?: boolean
  label?: string
}

const spring = { type: 'spring', stiffness: 260, damping: 18 } as const

export function Face({ mood, color, size = 88, dimmed = false, label }: FaceProps) {
  const f = FACES[mood] ?? FACES.neutral
  const gradientId = `face-${color.replace('#', '')}`
  // deterministic per-color blink offset so the table doesn't blink in unison
  const blinkDelay = (parseInt(color.slice(1, 3), 16) % 30) / 10

  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      role="img"
      aria-label={label ?? `${mood} face`}
      style={{ filter: dimmed ? 'grayscale(1) brightness(0.6)' : undefined, overflow: 'visible' }}
    >
      <defs>
        <radialGradient id={gradientId} cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor={color} stopOpacity="0.95" />
          <stop offset="100%" stopColor="#07060d" stopOpacity="0.95" />
        </radialGradient>
      </defs>

      {/* head */}
      <circle cx="50" cy="52" r="42" fill={`url(#${gradientId})`} stroke={color} strokeWidth="2.5" />
      <ellipse cx="36" cy="30" rx="12" ry="6" fill="white" opacity="0.12" transform="rotate(-25 36 30)" />

      {/* brows */}
      <motion.g animate={{ y: f.browY - 31 }} transition={spring}>
        <motion.rect x="25" y="29" width="18" height="3.6" rx="1.8" fill="#f3efe4"
          style={{ originX: '34px', originY: '31px' }} animate={{ rotate: f.browL }} transition={spring} />
        <motion.rect x="57" y="29" width="18" height="3.6" rx="1.8" fill="#f3efe4"
          style={{ originX: '66px', originY: '31px' }} animate={{ rotate: f.browR }} transition={spring} />
      </motion.g>

      {/* eyes with idle blink */}
      <motion.g
        style={{ originY: '44px' }}
        animate={{ scaleY: [1, 1, 0.1, 1] }}
        transition={{ duration: 4.2, times: [0, 0.92, 0.96, 1], repeat: Infinity, delay: blinkDelay }}
      >
        {[36, 64].map((cx) => (
          <g key={cx}>
            <motion.ellipse cx={cx} cy="44" rx="7" fill="#f3efe4" animate={{ ry: f.eyeRy }} transition={spring} />
            <motion.circle cy="44" r="3" fill="#07060d" animate={{ cx: cx + f.pupilDx, r: Math.min(3, f.eyeRy * 0.6) }} transition={spring} />
            {f.lids && <rect x={cx - 8} y="35.5" width="16" height="6" fill={color} opacity="0.85" rx="2" />}
          </g>
        ))}
      </motion.g>

      {/* mouth */}
      <motion.path animate={{ d: mouthPath(f.mouth) }} transition={spring} fill="#07060d" stroke="#f3efe4" strokeWidth="2.2" strokeLinejoin="round" />

      {/* mood props */}
      <AnimatePresence>
        {f.blush && (
          <motion.g key="blush" initial={{ opacity: 0 }} animate={{ opacity: 0.55 }} exit={{ opacity: 0 }}>
            <ellipse cx="24" cy="58" rx="6" ry="3.5" fill="#ff2e88" />
            <ellipse cx="76" cy="58" rx="6" ry="3.5" fill="#ff2e88" />
          </motion.g>
        )}
        {f.sweat && (
          <motion.path key="sweat" d="M 84 30 Q 90 40 84 44 Q 78 40 84 30 Z" fill="#3df5ff"
            initial={{ opacity: 0, y: -6 }} animate={{ opacity: 0.9, y: [0, 4, 0] }} exit={{ opacity: 0 }}
            transition={{ y: { repeat: Infinity, duration: 1.6 } }} />
        )}
        {f.tear && (
          <motion.path key="tear" d="M 36 52 Q 39 60 36 63 Q 33 60 36 52 Z" fill="#3df5ff"
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 0.9, y: [0, 8] }} exit={{ opacity: 0 }}
            transition={{ y: { repeat: Infinity, duration: 1.4 } }} />
        )}
        {f.steam && (
          <motion.g key="steam" initial={{ opacity: 0 }} animate={{ opacity: [0.3, 0.9, 0.3] }} exit={{ opacity: 0 }}
            transition={{ repeat: Infinity, duration: 0.9 }} stroke="#ff2e88" strokeWidth="3" strokeLinecap="round" fill="none">
            <path d="M 14 22 q 4 -6 0 -12" />
            <path d="M 86 22 q -4 -6 0 -12" />
          </motion.g>
        )}
        {f.sparkle && (
          <motion.g key="sparkle" initial={{ scale: 0 }} animate={{ scale: [0.8, 1.15, 0.8], rotate: [0, 20, 0] }}
            exit={{ scale: 0 }} transition={{ repeat: Infinity, duration: 1.2 }} fill="#ffc940" style={{ originX: '86px', originY: '18px' }}>
            <path d="M 86 8 L 89 16 L 97 18 L 89 20 L 86 28 L 83 20 L 75 18 L 83 16 Z" />
          </motion.g>
        )}
      </AnimatePresence>
    </svg>
  )
}
