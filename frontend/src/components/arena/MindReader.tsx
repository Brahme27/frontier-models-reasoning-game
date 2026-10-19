import { AnimatePresence, motion } from 'motion/react'
import { X } from 'lucide-react'
import { useEffect } from 'react'

import { DECISION_STYLE, MOOD_EMOJI } from '../../lib/moods'
import type { PlayerView } from '../../lib/reducer'
import { Face } from '../Face'
import { Chip } from '../ui'

export function MindReader({ player, onClose }: { player: PlayerView | null; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <AnimatePresence>
      {player && (
        <>
          <motion.div key="scrim" className="fixed inset-0 z-40 bg-ink/60 backdrop-blur-sm" onClick={onClose}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.aside key="panel" role="dialog" aria-modal="true" aria-label={`Mind reader: ${player.name}`}
            className="panel fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col overflow-y-auto p-6"
            initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', damping: 26, stiffness: 240 }}>
            <button onClick={onClose} aria-label="Close" className="absolute top-4 right-4 grid h-11 w-11 place-items-center rounded-full text-dust hover:bg-white/5">
              <X size={18} />
            </button>
            <div className="flex items-center gap-4">
              <Face mood={player.mood} color={player.color} size={96} />
              <div>
                <p className="font-mono text-[10px] tracking-[0.3em] text-cyan uppercase">Mind reader</p>
                <h2 className="font-display text-3xl">{player.name}</h2>
                <p className="text-sm" style={{ color: player.color }}>{player.emoji} {player.display_name} · {player.lab}</p>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-1.5">
              <Chip color="var(--color-gold)">◉ {player.coins} coins</Chip>
              <Chip>{MOOD_EMOJI[player.mood]} {player.mood}</Chip>
              <Chip color="var(--color-cyan)">reasoning: {player.reasoning}</Chip>
              <Chip>{player.provider}</Chip>
              {player.latencyMs > 0 && <Chip>{(player.latencyMs / 1000).toFixed(1)}s think time</Chip>}
              {player.fallbacks > 0 && <Chip color="var(--color-pink)">{player.fallbacks} stumble(s)</Chip>}
            </div>

            {player.decision && (
              <section className="mt-6">
                <h3 className="font-mono text-[11px] tracking-[0.25em] text-dust uppercase">Last decision quality</h3>
                <p className="mt-1 font-display text-xl" style={{ color: DECISION_STYLE[player.decision.label].color }}>
                  {DECISION_STYLE[player.decision.label].icon} {DECISION_STYLE[player.decision.label].label}
                </p>
                <p className="mt-1 text-sm text-dust">
                  Gained {player.decision.actualDelta >= 0 ? '+' : ''}{player.decision.actualDelta}; the best possible move (given everyone else's
                  choices) would have gained {player.decision.bestDelta >= 0 ? '+' : ''}{player.decision.bestDelta}.
                  {' '}That gap is called <strong className="text-chalk">regret</strong>.
                </p>
              </section>
            )}

            <section className="mt-6">
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-dust uppercase">💭 Private thought</h3>
              <p className="mt-2 rounded-xl border border-dashed border-cyan/50 p-3 text-cyan italic">{player.thought ?? 'Nothing yet.'}</p>
            </section>

            <section className="mt-6">
              <h3 className="font-mono text-[11px] tracking-[0.25em] text-dust uppercase">🧠 Native chain-of-thought</h3>
              {player.cot ? (
                <pre className="scrollbar-thin mt-2 max-h-80 overflow-auto rounded-xl bg-ink p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-chalk/80">
                  {player.cot}
                </pre>
              ) : (
                <p className="mt-2 text-sm text-dust">
                  This model did not expose hidden reasoning tokens for its last turn. Non-reasoning models only “think” through the prompted private thought.
                </p>
              )}
            </section>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
