import { AnimatePresence, motion } from 'motion/react'
import { Brain, Lock, Skull } from 'lucide-react'

import { DECISION_STYLE, MOOD_COLOR, MOOD_EMOJI } from '../../lib/moods'
import type { PlayerView } from '../../lib/reducer'
import { Face } from '../Face'
import { AnimatedNumber } from '../ui'

interface Props {
  player: PlayerView
  isWinner: boolean
  onSelect: () => void
}

export function PlayerSeat({ player: p, isWinner, onSelect }: Props) {
  const decision = p.decision ? DECISION_STYLE[p.decision.label] : null

  return (
    <motion.button
      type="button"
      onClick={onSelect}
      aria-label={`${p.name}, played by ${p.display_name}. ${p.coins} coins, feeling ${p.mood}. Open mind reader.`}
      className={`group relative flex w-[clamp(8rem,14vw,11rem)] flex-col items-center rounded-3xl px-3 pt-2.5 pb-3 text-center
        panel transition-transform hover:-translate-y-1`}
      style={{ color: p.color, boxShadow: `0 0 0 1px ${p.color}55, 0 0 36px ${p.color}33` }}
      animate={isWinner ? { scale: [1, 1.06, 1] } : { scale: 1 }}
      transition={isWinner ? { repeat: Infinity, duration: 1.6 } : undefined}
    >
      {/* thinking halo */}
      <div className="relative">
        <AnimatePresence>
          {p.thinking && (
            <motion.span
              key="halo"
              className="absolute -inset-2 rounded-full border-2 border-dashed"
              style={{ borderColor: p.color }}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1, rotate: 360 }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={{ rotate: { repeat: Infinity, duration: 3, ease: 'linear' } }}
            />
          )}
        </AnimatePresence>
        <Face mood={p.mood} color={p.color} size={60} dimmed={!p.alive} label={`${p.name} looks ${p.mood}`} />
        {isWinner && <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-2xl" aria-hidden>👑</span>}
      </div>

      <p className="mt-1 font-display text-lg leading-none text-chalk">{p.name}</p>
      <p className="mt-1 max-w-full truncate font-mono text-[10px] tracking-wider uppercase" style={{ color: p.color }}>
        {p.emoji} {p.display_name}
      </p>

      <div className="mt-2 flex items-baseline gap-1">
        <span aria-hidden className="text-gold">◉</span>
        <AnimatedNumber value={p.coins} className="font-mono text-2xl font-semibold text-gold tabular-nums neon-text" />
        <AnimatePresence>
          {p.lastDelta !== 0 && (
            <motion.span
              key={`${p.lastDelta}-${p.coins}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`font-mono text-sm font-semibold ${p.lastDelta > 0 ? 'text-lime' : 'text-pink'}`}
            >
              {p.lastDelta > 0 ? '+' : ''}{p.lastDelta}
            </motion.span>
          )}
        </AnimatePresence>
      </div>

      <div className="mt-2 flex min-h-6 flex-wrap items-center justify-center gap-1">
        <span className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] capitalize" style={{ color: MOOD_COLOR[p.mood] }}>
          {MOOD_EMOJI[p.mood]} {p.mood}
        </span>
        {p.locked && (
          <span className="inline-flex items-center gap-1 rounded-full bg-cyan/10 px-2 py-0.5 text-[11px] text-cyan">
            <Lock size={11} aria-hidden /> locked
          </span>
        )}
      </div>

      <AnimatePresence>
        {decision && p.decision && (
          <motion.div
            key={p.decision.label}
            initial={{ opacity: 0, scale: 0.6, rotate: -8 }}
            animate={{ opacity: 1, scale: 1, rotate: -4 }}
            exit={{ opacity: 0 }}
            className="absolute -right-3 -bottom-3 rounded-md px-2 py-1 font-display text-[10px] tracking-wider uppercase neon-box"
            style={{ color: decision.color, background: 'var(--color-ink)' }}
            title={p.decision.regret ? `Left ${p.decision.regret} coin(s) on the table` : 'Best possible move given what others did'}
          >
            {decision.icon} {decision.label}{p.decision.regret > 0 ? ` −${p.decision.regret}` : ''}
          </motion.div>
        )}
      </AnimatePresence>

      {!p.alive && (
        <div className="absolute inset-0 grid place-items-center rounded-3xl bg-ink/70">
          <span className="flex -rotate-12 items-center gap-1 border-2 border-pink px-2 py-1 font-display text-sm text-pink">
            <Skull size={14} aria-hidden /> Eliminated
          </span>
        </div>
      )}

      <span className="absolute top-2 right-2 text-dust opacity-0 transition-opacity group-hover:opacity-100" aria-hidden>
        <Brain size={14} />
      </span>
    </motion.button>
  )
}
