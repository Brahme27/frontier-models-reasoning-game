import { AnimatePresence, motion } from 'motion/react'

import type { PlayerView } from '../../lib/reducer'
import type { EmotionTag } from '../../lib/types'
import type { SeatGeometry } from './layout'

export function SpeechBubble({ player, geometry, tag }: { player: PlayerView; geometry: SeatGeometry; tag?: EmotionTag }) {
  const pos = geometry.speech
  const sus = tag ? Math.round(tag.deception * 100) : null
  return (
    <AnimatePresence mode="popLayout">
      {player.speech && player.alive && (
        <motion.div
          key={player.speech.seq}
          className="pointer-events-none absolute z-20 hidden w-[min(23%,15rem)] md:block"
          style={{ left: `${pos.x}%`, top: `${pos.y}%`, x: '-50%', y: '-50%' }}
          initial={{ opacity: 0, scale: 0.7, y: '-30%' }}
          animate={{ opacity: 1, scale: 1, y: '-50%' }}
          exit={{ opacity: 0, scale: 0.9 }}
          transition={{ type: 'spring', stiffness: 300, damping: 22 }}
        >
          <div className="relative rounded-2xl bg-chalk px-3.5 py-2.5 text-[13px] leading-snug font-medium text-ink shadow-xl"
            style={{ boxShadow: `0 8px 30px ${player.color}55` }}>
            <span className="mb-0.5 block font-display text-[10px] tracking-wider" style={{ color: player.color }}>
              {player.name} says
            </span>
            “{player.speech.text}”
            {tag && (
              <span className="mt-1.5 flex items-center gap-2 font-mono text-[10px] text-ink/60">
                <span className="italic">{tag.tone}</span>
                {sus !== null && sus >= 40 && <span className="rounded bg-pink px-1 text-chalk">🕵 {sus}% sus</span>}
              </span>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function ThoughtBubble({ player, geometry, visible }: { player: PlayerView; geometry: SeatGeometry; visible: boolean }) {
  const pos = geometry.thought
  return (
    <AnimatePresence>
      {visible && player.thought && player.alive && (
        <motion.div
          key={player.thought}
          className="pointer-events-none absolute z-10 hidden w-[min(21%,13rem)] lg:block"
          style={{ left: `${pos.x}%`, top: `${pos.y}%`, x: '-50%', y: '-50%' }}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
        >
          <div className="rounded-[1.4rem] border border-dashed border-cyan/60 bg-ink/85 px-3 py-2 text-[12px] leading-snug text-cyan italic">
            <span className="mb-0.5 block font-mono text-[9px] tracking-[0.2em] not-italic uppercase opacity-70">
              💭 secretly thinks
            </span>
            {player.thought}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
