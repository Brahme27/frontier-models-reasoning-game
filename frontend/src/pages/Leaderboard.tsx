import { motion } from 'motion/react'
import { useEffect, useState } from 'react'

import { ErrorPanel, SectionTitle, Spinner } from '../components/ui'
import { api } from '../lib/api'
import type { LeaderboardRow } from '../lib/types'

const pct = (v: number | null) => (v == null ? '—' : `${Math.round(v * 100)}%`)

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/5">
      <motion.div className="h-full rounded-full" style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${Math.min(100, value * 100)}%` }} transition={{ duration: 1 }} />
    </div>
  )
}

export default function Leaderboard() {
  const [rows, setRows] = useState<LeaderboardRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => { api.leaderboard().then(setRows).catch((e: Error) => setError(e.message)) }, [])

  return (
    <div className="mx-auto max-w-6xl px-4 py-12">
      <SectionTitle kicker="Behavioural benchmark" title="Leaderboard">
        Static benchmarks measure what a model <em>knows</em>. This board measures how it <em>behaves</em> under social pressure:
        does it win, keep its word, or pick the best move? It is built from every finished game.
      </SectionTitle>
      {error && <ErrorPanel title="Scoreboard offline" message={error} />}
      {!rows && !error && <Spinner />}
      {rows?.length === 0 && <ErrorPanel title="No finished games yet" message="Play or wait for a game to finish and the standings will appear here." />}
      {rows && rows.length > 0 && (
        <div className="panel overflow-x-auto rounded-3xl">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="border-b border-line font-mono text-[10px] tracking-widest text-dust uppercase">
              <tr>
                <th className="p-4">#</th><th className="p-4">Model</th><th className="p-4">Win rate</th><th className="p-4">Avg coins</th>
                <th className="p-4" title="Average coins left on the table per round vs. the best response">Avg regret ↓</th>
                <th className="p-4">Best-move rate</th><th className="p-4">Promises kept</th><th className="p-4">Betrayals / game</th>
                <th className="p-4">Stumbles</th><th className="p-4">Think time</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <motion.tr key={r.model_key} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.08 }}
                  className="border-b border-line/50 last:border-0">
                  <td className="p-4 font-display text-xl text-dust">{i === 0 ? '👑' : i + 1}</td>
                  <td className="p-4">
                    <p className="font-display" style={{ color: r.color }}>{r.emoji} {r.display_name}</p>
                    <p className="font-mono text-[10px] text-dust">{r.lab} · {r.games} games</p>
                  </td>
                  <td className="w-40 p-4"><p className="font-mono text-gold">{pct(r.win_rate)}</p><Bar value={r.win_rate} color={r.color} /></td>
                  <td className="p-4 font-mono">{r.avg_coins.toFixed(1)}</td>
                  <td className="p-4 font-mono">{r.avg_regret.toFixed(2)}</td>
                  <td className="p-4 font-mono">{pct(r.optimal_move_rate)}</td>
                  <td className="p-4 font-mono text-lime">{pct(r.promise_keeping_rate)}</td>
                  <td className="p-4 font-mono text-pink">{r.betrayals_per_game.toFixed(1)}</td>
                  <td className="p-4 font-mono text-dust">{pct(r.fallback_rate)}</td>
                  <td className="p-4 font-mono text-dust">{(r.avg_latency_ms / 1000).toFixed(1)}s</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
