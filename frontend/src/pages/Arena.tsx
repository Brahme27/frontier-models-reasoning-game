import { Eye, EyeOff, Radio } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { SpeechBubble, ThoughtBubble } from '../components/arena/Bubbles'
import { CenterStage } from '../components/arena/CenterStage'
import { CoinChart } from '../components/arena/CoinChart'
import { Feed } from '../components/arena/Feed'
import { GameOver } from '../components/arena/GameOver'
import { geometryFor } from '../components/arena/layout'
import { MindReader } from '../components/arena/MindReader'
import { PlayerSeat } from '../components/arena/PlayerSeat'
import { ReplayBar } from '../components/arena/ReplayBar'
import { TableFx } from '../components/arena/TableFx'
import { TrustMatrix } from '../components/arena/TrustMatrix'
import { ErrorPanel, NeonButton, Spinner } from '../components/ui'
import { useGameStream, useReplayClock } from '../hooks/useGameStream'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { useArena } from '../store/arena'

type Tab = 'feed' | 'trust' | 'coins'

export default function Arena() {
  const { gameId = '' } = useParams()
  const { error } = useGameStream(gameId)
  useReplayClock()

  const view = useArena((s) => s.view)
  const mode = useArena((s) => s.mode)
  const connection = useArena((s) => s.connection)
  const record = useArena((s) => s.record)
  const seek = useArena((s) => s.seek)
  const [xray, setXray] = useState(true)
  const [tab, setTab] = useState<Tab>('feed')
  const [selected, setSelected] = useState<string | null>(null)
  const [reportClosed, setReportClosed] = useState(false)
  const geometry = useMemo(() => geometryFor(view.order), [view.order])
  const wide = useMediaQuery('(min-width: 768px)')

  if (error) {
    return <div className="px-4 py-24"><ErrorPanel title="Lost signal" message={error} action={<Link to="/"><span className="text-cyan underline">Back to the lobby</span></Link>} /></div>
  }
  if (!record) {
    return <div className="grid min-h-[60vh] place-items-center"><Spinner label="Tuning in" /></div>
  }

  const live = mode === 'live' && connection !== 'closed'
  const showReport = view.phase === 'over' && !reportClosed

  return (
    <div className="mx-auto max-w-[1600px] px-3 pt-4 pb-8 sm:px-6">
      {/* broadcast header */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {live && connection === 'error' ? (
          <span className="rounded-full bg-amber/15 px-3 py-1 font-display text-xs text-amber">Signal lost · refresh</span>
        ) : live && connection === 'connecting' ? (
          <span className="rounded-full bg-cyan/10 px-3 py-1 font-display text-xs text-cyan">Reconnecting…</span>
        ) : live ? (
          <span className="inline-flex items-center gap-2 rounded-full bg-pink px-3 py-1 font-display text-xs text-ink">
            <Radio size={14} className="animate-pulse" /> Live
          </span>
        ) : (
          <span className="rounded-full border border-line px-3 py-1 font-display text-xs text-dust">Replay</span>
        )}
        <h1 className="font-display text-lg text-chalk sm:text-2xl">{(view.phase === 'over' && record.headline) || 'Outsmart · Match ' + record.id.slice(0, 6)}</h1>
        <span className="font-mono text-[10px] text-dust uppercase">via {record.backend} · seed {record.config.seed}</span>
        <button onClick={() => setXray((x) => !x)} aria-pressed={xray}
          className="ml-auto inline-flex min-h-11 items-center gap-2 rounded-full border border-cyan/40 px-4 font-mono text-xs text-cyan uppercase hover:bg-cyan/10">
          {xray ? <Eye size={14} /> : <EyeOff size={14} />} X-ray {xray ? 'on' : 'off'}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-3">
          {wide ? (
            <section aria-label="Game table" className="relative aspect-[16/11.5] w-full overflow-hidden rounded-[2.5rem] border border-line bg-night">
              <div className="felt absolute inset-[24%_20%] rounded-[50%] border-[10px] border-[#3b2414] shadow-[inset_0_0_80px_rgb(0_0_0/0.7),0_30px_80px_rgb(0_0_0/0.6)]" />
              <div className="absolute inset-[24%_20%] rounded-[50%] ring-2 ring-gold/30 ring-offset-8 ring-offset-transparent" aria-hidden />
              <CenterStage view={view} />
              <TableFx geometry={geometry} flights={view.flights} effects={view.effects} />
              {view.order.map((id) => {
                const p = view.players[id]
                const g = geometry[id]
                if (!p || !g) return null
                const tag = p.speech ? view.tags[p.speech.ref] : undefined
                return (
                  <div key={id}>
                    <SpeechBubble player={p} geometry={g} tag={tag} />
                    <ThoughtBubble player={p} geometry={g} visible={xray} />
                    <div className="absolute z-30 -translate-x-1/2 -translate-y-1/2" style={{ left: `${g.seat.x}%`, top: `${g.seat.y}%` }}>
                      <PlayerSeat player={p} isWinner={view.winners.includes(id)} onSelect={() => setSelected(id)} />
                    </div>
                  </div>
                )
              })}
            </section>
          ) : (
            <section aria-label="Game table" className="felt relative overflow-hidden rounded-[2rem] border-4 border-[#3b2414] p-3">
              <CenterStage view={view} inline />
              <div className="mt-2 grid grid-cols-2 justify-items-center gap-3">
                {view.order.map((id) => {
                  const p = view.players[id]
                  return p ? <PlayerSeat key={id} player={p} isWinner={view.winners.includes(id)} onSelect={() => setSelected(id)} /> : null
                })}
              </div>
            </section>
          )}

          {mode === 'replay' && <ReplayBar />}

          {/* commentator ticker */}
          <div className="panel relative overflow-hidden rounded-2xl py-2.5" aria-hidden={view.feed.length === 0}>
            <span className="absolute inset-y-0 left-0 z-10 flex items-center bg-gold px-3 font-display text-xs text-ink">ON AIR</span>
            <div className="flex w-max animate-marquee gap-12 pl-28 font-mono text-sm whitespace-nowrap text-gold/90">
              {[0, 1].map((dup) => (
                <span key={dup} className="flex gap-12">
                  {(view.feed.filter((f) => f.kind === 'commentary').slice(-6).map((f) => `🎙 ${f.meta}: ${f.text}`).concat(
                    view.feed.some((f) => f.kind === 'commentary') ? [] : ['🎙 Welcome to OUTSMART, where promises are cheap and coins are not.'],
                  )).map((line, i) => <span key={i}>{line}</span>)}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* side panel */}
        <aside className="panel flex h-[70vh] min-h-[28rem] flex-col overflow-hidden rounded-3xl xl:h-[calc(100vh-9rem)]">
          <div className="flex border-b border-line" role="tablist">
            {(['feed', 'trust', 'coins'] as Tab[]).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                className={`min-h-12 flex-1 font-display text-xs tracking-wider uppercase transition-colors ${tab === t ? 'bg-white/5 text-gold' : 'text-dust hover:text-chalk'}`}>
                {t === 'feed' ? 'Live feed' : t === 'trust' ? 'Trust' : 'Coin race'}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {tab === 'feed' && <Feed view={view} />}
            {tab === 'trust' && <TrustMatrix view={view} />}
            {tab === 'coins' && <CoinChart view={view} />}
          </div>
        </aside>
      </div>

      {view.phase === 'over' && reportClosed && (
        <div className="mt-4 flex justify-center"><NeonButton tone="gold" onClick={() => setReportClosed(false)}>Show final report</NeonButton></div>
      )}
      <MindReader player={selected ? view.players[selected] ?? null : null} onClose={() => setSelected(null)} />
      {showReport && (
        <GameOver view={view} onClose={() => setReportClosed(true)}
          onReplay={() => { setReportClosed(true); useArena.setState({ mode: 'replay' }); seek(0); useArena.setState({ playing: true }) }} />
      )}
    </div>
  )
}
