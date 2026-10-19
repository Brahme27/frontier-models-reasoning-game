import { motion } from 'motion/react'
import { RotateCcw, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import type { GameView } from '../../lib/reducer'
import { Face } from '../Face'
import { NeonButton, Spinner } from '../ui'

const VERDICT_COLOR = { brilliant: 'var(--color-lime)', good: 'var(--color-cyan)', bad: 'var(--color-amber)', terrible: 'var(--color-pink)' }

export function GameOver({ view, onReplay, onClose }: { view: GameView; onReplay: () => void; onClose: () => void }) {
  const ranked = [...view.order].sort((a, b) => (view.players[b]?.coins ?? 0) - (view.players[a]?.coins ?? 0))
  const byName = Object.fromEntries(Object.values(view.players).map((p) => [p.name, p]))
  const report = view.report
  const navigate = useNavigate()

  return (
    <motion.div className="fixed inset-0 z-50 overflow-y-auto bg-ink/85 backdrop-blur-md" role="dialog" aria-modal="true" aria-label="Game over"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="mx-auto max-w-5xl px-4 py-10">
        <div className="flex justify-end">
          <button onClick={onClose} aria-label="Close report" className="grid h-11 w-11 place-items-center rounded-full text-dust hover:bg-white/5"><X /></button>
        </div>
        <motion.p initial={{ scale: 2, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ type: 'spring', damping: 12 }}
          className="text-center font-display text-5xl text-gold neon-text animate-flicker sm:text-7xl">GAME OVER</motion.p>

        {/* podium */}
        <div className="mt-10 grid grid-cols-2 items-end gap-4 sm:grid-cols-4">
          {ranked.map((id, i) => {
            const p = view.players[id]
            if (!p) return null
            const s = view.stats[id]
            return (
              <motion.div key={id} initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.3 + i * 0.15 }}
                className="panel flex flex-col items-center rounded-3xl p-4 text-center" style={{ boxShadow: `0 0 40px ${p.color}${i === 0 ? '66' : '22'}` }}>
                <span className="font-display text-2xl text-dust">#{i + 1}</span>
                <Face mood={view.winners.includes(id) ? 'gleeful' : p.mood} color={p.color} size={i === 0 ? 96 : 72} dimmed={!p.alive} />
                <p className="mt-1 font-display text-xl">{view.winners.includes(id) ? '👑 ' : ''}{p.name}</p>
                <p className="text-xs" style={{ color: p.color }}>{p.display_name}</p>
                <p className="mt-2 font-mono text-3xl font-semibold text-gold">{p.coins}</p>
                {s && (
                  <dl className="mt-3 grid w-full grid-cols-2 gap-x-2 gap-y-1 text-left font-mono text-[10px] text-dust">
                    <dt>avg regret</dt><dd className="text-right text-chalk">{s.avg_regret.toFixed(2)}</dd>
                    <dt>best moves</dt><dd className="text-right text-chalk">{s.optimal_moves}/{s.rounds}</dd>
                    <dt>promises kept</dt><dd className="text-right text-chalk">{s.pledges_made ? `${s.pledges_kept}/${s.pledges_made}` : '—'}</dd>
                    <dt>betrayals</dt><dd className="text-right text-pink">{s.betrayals}</dd>
                    <dt>think time</dt><dd className="text-right text-chalk">{(s.avg_latency_ms / 1000).toFixed(1)}s</dd>
                  </dl>
                )}
              </motion.div>
            )
          })}
        </div>

        {!report && <div className="mt-10 flex justify-center"><Spinner label="The analyst is writing the report" /></div>}
        {report && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.8 }}>
            <h2 className="mt-12 text-center font-display text-2xl text-chalk sm:text-3xl">{report.headline}</h2>
            <p className="mx-auto mt-3 max-w-2xl text-center text-dust">{report.summary}</p>

            <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {report.awards.map((a, i) => (
                <motion.div key={`${i}-${a.title}`} initial={{ rotateY: 90, opacity: 0 }} animate={{ rotateY: 0, opacity: 1 }} transition={{ delay: 1 + i * 0.2 }}
                  className="panel rounded-2xl p-4" style={{ borderColor: byName[a.player]?.color }}>
                  <p className="text-3xl" aria-hidden>{a.emoji}</p>
                  <p className="mt-2 font-display text-sm text-gold">{a.title}</p>
                  <p className="font-display text-lg" style={{ color: byName[a.player]?.color }}>{a.player}</p>
                  <p className="mt-1 text-sm text-dust">{a.reason}</p>
                </motion.div>
              ))}
            </div>

            {report.decisions.length > 0 && (
              <section className="mt-10">
                <h3 className="font-display text-lg">Key decisions</h3>
                <ul className="mt-3 space-y-2">
                  {report.decisions.map((d, i) => (
                    <li key={i} className="panel flex gap-3 rounded-xl p-3">
                      <span className="font-display text-xs uppercase" style={{ color: VERDICT_COLOR[d.verdict] }}>{d.verdict}</span>
                      <span className="text-sm"><strong style={{ color: byName[d.player]?.color }}>{d.player}</strong> (round {d.round}): <span className="text-dust">{d.explanation}</span></span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {report.insights.length > 0 && (
              <section className="mt-10 grid gap-3 sm:grid-cols-2">
                {report.insights.map((ins, i) => (
                  <div key={`${i}-${ins.player}`} className="panel rounded-xl p-4">
                    <p className="font-display" style={{ color: byName[ins.player]?.color }}>{ins.player} <span className="text-xs text-dust">· {byName[ins.player]?.display_name}</span></p>
                    <p className="mt-1 text-sm text-chalk">Style: <em>{ins.style}</em></p>
                    <p className="text-sm text-dust">{ins.reasoning_quality}</p>
                  </div>
                ))}
              </section>
            )}
            <p className="mt-6 text-center font-mono text-[10px] text-dust uppercase">Report by {report.generated_by === 'llm' ? 'the AI analyst (a neutral model from a non-competing lab)' : 'the built-in template analyst'}</p>
          </motion.div>
        )}

        <div className="mt-10 flex flex-wrap justify-center gap-3">
          <NeonButton tone="gold" onClick={onReplay}><RotateCcw size={16} /> Watch the replay</NeonButton>
          <NeonButton tone="ghost" onClick={() => navigate('/')}>Back to lobby</NeonButton>
        </div>
      </div>
    </motion.div>
  )
}
