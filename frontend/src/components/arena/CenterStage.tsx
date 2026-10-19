import { AnimatePresence, motion } from 'motion/react'

import type { GameView } from '../../lib/reducer'

const PHASE_LABEL: Record<GameView['phase'], string> = {
  waiting: 'Shuffling seats…',
  negotiate: 'Negotiating',
  move: 'Secret moves',
  reveal: 'The reveal',
  over: 'Game over',
  error: 'Technical difficulties',
}

export function CenterStage({ view, inline = false }: { view: GameView; inline?: boolean }) {
  const phase = view.phase === 'negotiate' && view.subround ? `${PHASE_LABEL.negotiate} · chat ${view.subround}` : PHASE_LABEL[view.phase]
  const c = view.commentary

  return (
    <div className={inline ? 'flex flex-col items-center py-3 text-center' : 'absolute top-1/2 left-1/2 z-20 flex w-[min(40%,24rem)] -translate-x-1/2 -translate-y-1/2 flex-col items-center text-center'}>
      <p className="font-mono text-[11px] tracking-[0.35em] text-dust uppercase">
        Round <span className="text-chalk">{Math.max(view.round, 0)}</span> / {view.maxRounds}
      </p>
      <motion.p key={phase} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
        className="mt-1 font-display text-sm tracking-wider text-cyan uppercase neon-text sm:text-base">
        {phase}
      </motion.p>

      <div className="mt-3 min-h-[5.5rem]" aria-live="polite">
        <AnimatePresence mode="wait">
          {c && (
            <motion.div key={c.seq} initial={{ opacity: 0, scale: 1.6, rotate: -3 }} animate={{ opacity: 1, scale: 1, rotate: -2 }}
              exit={{ opacity: 0, scale: 0.8 }} transition={{ type: 'spring', stiffness: 220, damping: 14 }}>
              <p className="font-display text-2xl leading-none text-gold neon-text animate-flicker sm:text-4xl">{c.headline}</p>
              <p className="mt-2 hidden text-sm leading-snug text-chalk/90 sm:block">{c.line}</p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* rotation progress */}
      <div className="mt-2 flex gap-1" aria-hidden>
        {Array.from({ length: view.maxRounds }, (_, i) => (
          <span key={i} className={`h-1.5 w-3 rounded-full transition-colors ${i < view.round ? 'bg-gold' : 'bg-white/10'}`} />
        ))}
      </div>
    </div>
  )
}
