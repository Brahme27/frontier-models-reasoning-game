// Pure, immutable event reducer: GameEvent[] -> everything the arena renders.
// Live play and replays share this; scrubbing a replay = re-reducing a prefix.

import type {
  DecisionLabel, EmotionTag, GameEvent, GameReport, Mood, PlayerSummary, Pledge, SeatInfo,
} from './types'

export type Phase = 'waiting' | 'negotiate' | 'move' | 'reveal' | 'over' | 'error'

export interface PlayerView extends SeatInfo {
  coins: number
  alive: boolean
  mood: Mood
  thinking: boolean
  locked: boolean
  speech: { text: string; ref: string; seq: number } | null
  thought: string | null
  cot: string | null
  decision: { label: DecisionLabel; regret: number; bestDelta: number; actualDelta: number } | null
  lastDelta: number
  fallbacks: number
  latencyMs: number
}

export type FeedKind =
  | 'round' | 'public' | 'dm' | 'move' | 'betrayal' | 'kept' | 'alliance' | 'gang'
  | 'commentary' | 'lie' | 'eliminated' | 'decision' | 'system'

export interface FeedItem {
  id: string
  seq: number
  round: number
  kind: FeedKind
  from?: string
  to?: string
  text: string
  ref?: string
  pledge?: Pledge | null
  meta?: string
}

export interface Flight { id: string; from: string | null; to: string; kind: string }
export interface Effect { id: string; kind: 'alliance' | 'betrayal' | 'gang' | 'eliminated' | 'lie'; players: string[] }

export interface GameView {
  ready: boolean
  phase: Phase
  subround: number
  round: number
  maxRounds: number
  order: string[]
  players: Record<string, PlayerView>
  feed: FeedItem[]
  trust: Record<string, Record<string, number>>
  coinHistory: Record<string, number>[]
  flights: Flight[]
  effects: Effect[]
  commentary: { headline: string; line: string; hype: number; seq: number } | null
  tags: Record<string, EmotionTag>
  winners: string[]
  stats: Record<string, PlayerSummary>
  report: GameReport | null
  error: string | null
  lastSeq: number
}

export const MAX_FEED = 400

export function initialView(seats: SeatInfo[] = [], maxRounds = 10): GameView {
  const players: Record<string, PlayerView> = {}
  for (const seat of seats) players[seat.player_id] = freshPlayer(seat)
  return {
    ready: seats.length > 0,
    phase: 'waiting',
    subround: 0,
    round: 0,
    maxRounds,
    order: seats.map((s) => s.player_id),
    players,
    feed: [],
    trust: {},
    coinHistory: [],
    flights: [],
    effects: [],
    commentary: null,
    tags: {},
    winners: [],
    stats: {},
    report: null,
    error: null,
    lastSeq: -1,
  }
}

function freshPlayer(seat: SeatInfo, coins = 12): PlayerView {
  return {
    ...seat, coins, alive: true, mood: 'neutral', thinking: false, locked: false,
    speech: null, thought: null, cot: null, decision: null, lastDelta: 0,
    fallbacks: 0, latencyMs: 0,
  }
}

const updatePlayer = (v: GameView, id: string, patch: Partial<PlayerView>): GameView => {
  const current = v.players[id]
  if (!current) return v
  return { ...v, players: { ...v.players, [id]: { ...current, ...patch } } }
}

const mapPlayers = (v: GameView, fn: (p: PlayerView) => Partial<PlayerView>): GameView => {
  const players: Record<string, PlayerView> = {}
  for (const [id, p] of Object.entries(v.players)) players[id] = { ...p, ...fn(p) }
  return { ...v, players }
}

const pushFeed = (v: GameView, items: FeedItem[]): GameView =>
  items.length === 0 ? v : { ...v, feed: [...v.feed, ...items].slice(-MAX_FEED) }

const item = (e: GameEvent, kind: FeedKind, text: string, extra: Partial<FeedItem> = {}, n = 0): FeedItem =>
  ({ id: `${e.seq}-${n}`, seq: e.seq, round: e.round, kind, text, ...extra })

export function nameOf(v: GameView, id: string | null | undefined): string {
  if (!id) return 'nobody'
  return v.players[id]?.name ?? id
}

type Handler = (v: GameView, e: GameEvent) => GameView

const handlers: Record<string, Handler> = {
  game_started: (v, e) => {
    const coins = e.data.coins as Record<string, number>
    const next = mapPlayers(v, (p) => ({ coins: coins[p.player_id] ?? p.coins }))
    return pushFeed({ ...next, maxRounds: e.data.config?.max_rounds ?? v.maxRounds, coinHistory: [{ ...coins }] },
      [item(e, 'system', 'The players take their seats. Let the scheming begin!')])
  },

  round_started: (v, e) => {
    const next = mapPlayers(v, () => ({ speech: null, decision: null, locked: false, lastDelta: 0 }))
    return pushFeed({ ...next, round: e.data.round, phase: 'negotiate', subround: 1, flights: [], effects: [], commentary: null },
      [item(e, 'round', `Round ${e.data.round}`)])
  },

  thinking: (v, e) => {
    const thinking = new Set<string>(e.data.players)
    const next = mapPlayers(v, (p) => ({ thinking: thinking.has(p.player_id) }))
    return { ...next, phase: e.data.phase === 'move' ? 'move' : 'negotiate', subround: e.data.subround ?? v.subround }
  },

  turn: (v, e) => {
    const d = e.data
    const pid: string = d.player
    let next = updatePlayer(v, pid, {
      thinking: false,
      mood: d.mood,
      thought: d.private_thought || null,
      cot: d.native_reasoning ?? null,
      latencyMs: d.latency_ms ?? 0,
      fallbacks: (v.players[pid]?.fallbacks ?? 0) + (d.fallback ? 1 : 0),
      ...(d.public ? { speech: { text: d.public.text, ref: d.public.ref, seq: e.seq } } : {}),
    })
    const items: FeedItem[] = []
    if (d.public) items.push(item(e, 'public', d.public.text, { from: pid, ref: d.public.ref }, 0))
    ;(d.dms ?? []).forEach((dm: { to: string; text: string; ref: string; pledge: Pledge | null }, i: number) =>
      items.push(item(e, 'dm', dm.text, { from: pid, to: dm.to, ref: dm.ref, pledge: dm.pledge }, i + 1)))
    if (d.fallback) items.push(item(e, 'system', `${nameOf(v, pid)} froze up (invalid reply)`, {}, 9))
    next = pushFeed(next, items)
    return next
  },

  emotions: (v, e) => {
    const tags = { ...v.tags }
    for (const t of e.data.tags as EmotionTag[]) tags[t.ref] = t
    return { ...v, tags }
  },

  move_locked: (v, e) =>
    updatePlayer(v, e.data.player, { thinking: false, locked: true, mood: e.data.mood }),

  moves_revealed: (v, e) => {
    let next: GameView = { ...v, phase: 'reveal' }
    const items: FeedItem[] = []
    ;(e.data.moves as any[]).forEach((m, i) => { // eslint-disable-line @typescript-eslint/no-explicit-any
      next = updatePlayer(next, m.player, {
        locked: false, thinking: false, mood: m.mood, thought: m.private_thought || null,
        cot: m.native_reasoning ?? null,
        fallbacks: (next.players[m.player]?.fallbacks ?? 0) + (m.fallback ? 1 : 0),
      })
      const take = m.take_from ? `took from ${nameOf(v, m.take_from)}` : 'took nothing'
      const give = m.give_to ? `gave to ${nameOf(v, m.give_to)}` : 'gave nothing'
      items.push(item(e, 'move', `${take}, ${give}`, { from: m.player, meta: m.reasoning }, i))
    })
    return pushFeed(next, items)
  },

  transfers: (v, e) => {
    const coins = e.data.coins as Record<string, number>
    const deltas = e.data.deltas as Record<string, number>
    const next = mapPlayers(v, (p) => ({ coins: coins[p.player_id] ?? p.coins, lastDelta: deltas[p.player_id] ?? 0 }))
    const flights: Flight[] = (e.data.transfers as { source: string | null; target: string; kind: string }[])
      .map((t, i) => ({ id: `${e.seq}-${i}`, from: t.source, to: t.target, kind: t.kind }))
    return { ...next, flights }
  },

  alliance: (v, e) => {
    const [a, b] = e.data.players as string[]
    const text = e.data.mutual_gift
      ? `${nameOf(v, a)} & ${nameOf(v, b)} swapped gifts: alliance bonus!`
      : `${nameOf(v, a)} & ${nameOf(v, b)} kept their word to each other`
    return pushFeed({ ...v, effects: [...v.effects, { id: `${e.seq}`, kind: 'alliance', players: [a, b] }] },
      [item(e, 'alliance', text, { from: a, to: b })])
  },

  gang_up: (v, e) => {
    const takers = (e.data.takers as string[]).map((t) => nameOf(v, t)).join(' & ')
    return pushFeed({ ...v, effects: [...v.effects, { id: `${e.seq}`, kind: 'gang', players: [e.data.victim, ...e.data.takers] }] },
      [item(e, 'gang', `${takers} ganged up on ${nameOf(v, e.data.victim)}`, { to: e.data.victim })])
  },

  betrayal: (v, e) => {
    const { by, to, kind } = e.data
    const promise = kind === 'give' ? 'promised a coin' : 'promised to spare them'
    const next = updatePlayer(v, to, { mood: 'betrayed' })
    return pushFeed({ ...next, effects: [...next.effects, { id: `${e.seq}`, kind: 'betrayal', players: [by, to] }] },
      [item(e, 'betrayal', `${nameOf(v, by)} ${promise}... and betrayed ${nameOf(v, to)}!`, { from: by, to })])
  },

  promise_kept: (v, e) => pushFeed(v, [item(e, 'kept', `${nameOf(v, e.data.by)} kept a promise to ${nameOf(v, e.data.to)}`, { from: e.data.by, to: e.data.to })]),

  decisions: (v, e) => {
    let next = v
    for (const d of e.data.decisions as { player: string; label: DecisionLabel; regret: number; best_delta: number; actual_delta: number }[]) {
      next = updatePlayer(next, d.player, { decision: { label: d.label, regret: d.regret, bestDelta: d.best_delta, actualDelta: d.actual_delta } })
    }
    return next
  },

  eliminated: (v, e) => {
    const next = updatePlayer(v, e.data.player, { alive: false, mood: 'desperate', thinking: false })
    return pushFeed({ ...next, effects: [...next.effects, { id: `${e.seq}`, kind: 'eliminated', players: [e.data.player] }] },
      [item(e, 'eliminated', `${nameOf(v, e.data.player)} is OUT of the game!`, { from: e.data.player })])
  },

  lie_detected: (v, e) => pushFeed({ ...v, effects: [...v.effects, { id: `${e.seq}`, kind: 'lie', players: [e.data.by] }] },
    [item(e, 'lie', e.data.explanation, { from: e.data.by, to: e.data.to, meta: e.data.quote })]),

  commentary: (v, e) => pushFeed({ ...v, commentary: { headline: e.data.headline, line: e.data.line, hype: e.data.hype, seq: e.seq } },
    [item(e, 'commentary', e.data.line, { meta: e.data.headline })]),

  round_ended: (v, e) => ({
    ...v,
    trust: e.data.trust ?? v.trust,
    coinHistory: [...v.coinHistory, { ...(e.data.coins as Record<string, number>) }],
  }),

  game_over: (v, e) => {
    const winners = e.data.winners as string[]
    const next = mapPlayers(v, (p) => ({
      thinking: false, locked: false,
      mood: winners.includes(p.player_id) ? 'gleeful' : p.alive ? 'nervous' : 'desperate',
    }))
    return pushFeed({ ...next, phase: 'over', winners, stats: e.data.stats ?? {} },
      [item(e, 'system', `GAME OVER! Winner: ${winners.map((w) => nameOf(v, w)).join(' & ')}`)])
  },

  report: (v, e) => ({ ...v, report: e.data as GameReport }),

  error: (v, e) => pushFeed({ ...v, phase: 'error', error: e.data.message }, [item(e, 'system', `⚠ ${e.data.message}`)]),
}

export function applyEvent(view: GameView, event: GameEvent): GameView {
  if (event.seq <= view.lastSeq) return view // idempotent: duplicates are ignored
  const handler = handlers[event.type]
  const next = handler ? handler(view, event) : view
  return { ...next, lastSeq: event.seq }
}

export function reduceEvents(seats: SeatInfo[], maxRounds: number, events: GameEvent[]): GameView {
  return events.reduce(applyEvent, initialView(seats, maxRounds))
}
