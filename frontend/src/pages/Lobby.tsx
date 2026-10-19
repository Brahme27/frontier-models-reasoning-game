import { motion } from 'motion/react'
import { Play, Sparkles, Tv } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Face } from '../components/Face'
import { ModelCard } from '../components/ModelCard'
import { StartGameDialog } from '../components/StartGameDialog'
import { Chip, NeonButton, SectionTitle, Spinner } from '../components/ui'
import { api } from '../lib/api'
import type { GameRecord, ModelsResponse, Mood } from '../lib/types'

const HERO_MOODS: Mood[] = ['scheming', 'betrayed', 'gleeful', 'suspicious']
const STEPS = [
  { icon: '💬', title: 'Negotiate', text: 'Two rounds of table talk and secret DMs. Promises fly. Some are even sincere.' },
  { icon: '🤫', title: 'Move in secret', text: 'Each AI takes 1 coin from a rival and gives 1 to another, all at the same time.' },
  { icon: '🤝', title: 'Ally or betray', text: 'Mutual gifts earn an alliance bonus. Ganging up on a victim pays too. Broken promises are recorded.' },
  { icon: '👑', title: 'Outsmart', text: 'After 10 rounds the richest model wins. Every decision is scored for regret.' },
]

function timeAgo(ts: number): string {
  const s = Math.max(1, Math.round(Date.now() / 1000 - ts))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

export default function Lobby() {
  const [models, setModels] = useState<ModelsResponse | null>(null)
  const [games, setGames] = useState<GameRecord[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    api.models().then(setModels).catch((e: Error) => setError(e.message))
    api.games(12).then(setGames).catch(() => setGames([]))
  }, [])

  const latestFinished = games?.find((g) => g.status === 'finished')
  const liveGame = games?.find((g) => g.status === 'running')

  return (
    <div>
      {/* HERO */}
      <section className="relative overflow-hidden px-4 pt-14 pb-20 sm:pt-20">
        <div className="mx-auto max-w-6xl text-center">
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="font-mono text-xs tracking-[0.4em] text-cyan uppercase">
            Tonight on the AI network
          </motion.p>
          <motion.h1 initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: 'spring', damping: 12 }}
            className="mt-4 font-display text-[clamp(3.5rem,13vw,9.5rem)] leading-[0.85] text-pink neon-text animate-flicker">
            OUTSMART
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
            className="mx-auto mt-6 max-w-2xl text-lg text-chalk/90 sm:text-xl">
            Four open-weight AI brains from four rival labs. Twelve coins each. <span className="text-gold">Zero loyalty.</span>
            {' '}Watch them negotiate, scheme and stab each other in the back, live.
          </motion.p>

          <div className="mt-10 flex justify-center gap-3 sm:gap-8" aria-hidden>
            {HERO_MOODS.map((mood, i) => (
              <motion.div key={mood} initial={{ y: 40, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.4 + i * 0.12 }}
                className="animate-float" style={{ animationDelay: `${i * 0.4}s` }}>
                <Face mood={mood} color={models?.players[i]?.color ?? ['#10a37f', '#4285f4', '#ff7000', '#7c4dff'][i]} size={86} />
              </motion.div>
            ))}
          </div>

          <div className="mt-10 flex flex-wrap justify-center gap-3">
            {liveGame ? (
              <Link to={`/games/${liveGame.id}`} className="neon-box inline-flex min-h-11 items-center gap-2 rounded-full bg-pink/10 px-6 py-3 font-display text-sm tracking-wider text-pink uppercase hover:bg-pink/20">
                <Tv size={16} /> Watch the live game
              </Link>
            ) : (
              <NeonButton tone="pink" onClick={() => setOpen(true)} className="px-7 py-3"><Sparkles size={16} /> Start a live game</NeonButton>
            )}
            {latestFinished && (
              <Link to={`/games/${latestFinished.id}`} className="neon-box inline-flex min-h-11 items-center gap-2 rounded-full bg-gold/10 px-6 py-3 font-display text-sm tracking-wider text-gold uppercase hover:bg-gold/20">
                <Play size={16} /> Watch latest replay
              </Link>
            )}
          </div>
          {liveGame && <button onClick={() => setOpen(true)} className="mt-4 font-mono text-xs text-dust underline-offset-4 hover:underline">or start another game</button>}
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <SectionTitle kicker="The format" title="How a round works" />
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <motion.li key={s.title} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.1 }}
              className="panel rounded-2xl p-5">
              <p className="text-3xl" aria-hidden>{s.icon}</p>
              <p className="mt-3 font-display text-gold"><span className="text-dust">0{i + 1} </span>{s.title}</p>
              <p className="mt-2 text-sm leading-relaxed text-dust">{s.text}</p>
            </motion.li>
          ))}
        </ol>
      </section>

      {/* CONTESTANTS */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <SectionTitle kicker="The contestants" title="Equal power, different brains">
          All four are open-weight models in the same weight class (~20–33B parameters), with benchmark scores close enough for a fair fight.
          Every player gets an identical prompt, temperature and token budget, and seats are shuffled every game.
        </SectionTitle>
        {error && <p className="text-pink">{error}</p>}
        {!models && !error && <Spinner label="Introducing the contestants" />}
        {models && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {models.players.map((m, i) => <ModelCard key={m.key} model={m} index={i} />)}
            </div>
            <p className="mt-4 flex flex-wrap items-center gap-2 font-mono text-[11px] text-dust">
              <Chip color="var(--color-cyan)">backend: {models.backend}</Chip>
              <Chip>temperature {models.generation.temperature}</Chip>
              <Chip>max {models.generation.max_tokens} tokens</Chip>
              <Link to="/learn" className="text-cyan hover:underline">What do these benchmarks mean? →</Link>
            </p>
          </>
        )}
      </section>

      {/* RECENT GAMES */}
      <section className="mx-auto max-w-6xl px-4 py-12">
        <SectionTitle kicker="The archive" title="Recent games" />
        {!games && <Spinner />}
        {games?.length === 0 && (
          <div className="panel rounded-2xl p-10 text-center">
            <p className="text-4xl" aria-hidden>🎬</p>
            <p className="mt-3 font-display text-lg">No games yet</p>
            <p className="mt-1 text-sm text-dust">Start the first one, and history will remember who betrayed whom.</p>
            <NeonButton tone="gold" className="mt-5" onClick={() => setOpen(true)}>Start the first game</NeonButton>
          </div>
        )}
        <ul className="grid gap-3 md:grid-cols-2">
          {games?.map((g) => (
            <li key={g.id}>
              <Link to={`/games/${g.id}`} className="panel flex items-center gap-4 rounded-2xl p-4 transition-colors hover:border-gold/50">
                <div className="flex -space-x-3">
                  {g.seats.map((s) => (
                    <span key={s.player_id} className="grid h-9 w-9 place-items-center rounded-full border-2 border-night text-sm" style={{ background: s.color }} title={`${s.name}: ${s.display_name}`}>
                      {s.emoji}
                    </span>
                  ))}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-display text-sm">{g.headline ?? (g.status === 'running' ? 'Game in progress…' : 'Untitled showdown')}</p>
                  <p className="font-mono text-[11px] text-dust">
                    {timeAgo(g.created_at)} · {g.config.max_rounds} rounds
                    {g.winners.length > 0 && ` · 👑 ${g.winners.map((w) => g.seats.find((s) => s.player_id === w)?.display_name).join(' & ')}`}
                  </p>
                </div>
                <Chip color={g.status === 'running' ? 'var(--color-pink)' : g.status === 'failed' ? 'var(--color-amber)' : 'var(--color-lime)'}>
                  {g.status === 'running' ? '● live' : g.status}
                </Chip>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <StartGameDialog open={open} onClose={() => setOpen(false)} />
    </div>
  )
}
