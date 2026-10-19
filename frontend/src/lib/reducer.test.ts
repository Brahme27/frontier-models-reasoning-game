import { applyEvent, initialView, MAX_FEED, reduceEvents } from './reducer'
import type { GameEvent, SeatInfo } from './types'

const seats: SeatInfo[] = ['alex', 'blake', 'charlie', 'drew'].map((id) => ({
  player_id: id, name: id[0].toUpperCase() + id.slice(1), model_key: `m-${id}`, display_name: `Model ${id}`,
  lab: 'Lab', color: '#fff', emoji: '🤖', reasoning: 'none', provider: 'fake',
}))

let seq = 0
const ev = (type: string, data: Record<string, unknown>, round = 1): GameEvent =>
  ({ game_id: 'g', seq: seq++, type, round, ts: 0, data })

beforeEach(() => { seq = 0 })

const coins = { alex: 12, blake: 12, charlie: 12, drew: 12 }

describe('event reducer', () => {
  it('starts with every seat and no history', () => {
    const v = initialView(seats, 10)
    expect(v.order).toEqual(['alex', 'blake', 'charlie', 'drew'])
    expect(v.players.alex.coins).toBe(12)
    expect(v.phase).toBe('waiting')
  })

  it('tracks a full round: talk, lock, reveal, transfers, betrayal, decisions', () => {
    const events = [
      ev('game_started', { coins, config: { max_rounds: 5 } }, 0),
      ev('round_started', { round: 1, coins }),
      ev('thinking', { phase: 'negotiate', subround: 1, players: ['alex', 'blake'] }),
      ev('turn', {
        player: 'alex', subround: 1, mood: 'scheming', private_thought: 'betray Blake',
        native_reasoning: 'cot', public: { ref: 'r1', text: 'Trust me!' },
        dms: [{ to: 'blake', text: 'ally?', ref: 'r1dm', pledge: { by: 'alex', to: 'blake', kind: 'spare', target: null } }],
        fallback: false, latency_ms: 900,
      }),
      ev('emotions', { tags: [{ ref: 'r1', player: 'alex', emotion: 'smug', intensity: 0.8, deception: 0.9, tone: 'oily' }] }),
      ev('thinking', { phase: 'move', players: ['alex', 'blake'] }),
      ev('move_locked', { player: 'alex', mood: 'smug' }),
      ev('moves_revealed', { moves: [{ player: 'alex', take_from: 'blake', give_to: null, reasoning: 'greed', private_thought: 'heh', mood: 'gleeful', fallback: false }] }),
      ev('transfers', { transfers: [{ source: 'blake', target: 'alex', kind: 'take', amount: 1 }], deltas: { alex: 1, blake: -1 }, coins: { ...coins, alex: 13, blake: 11 } }),
      ev('betrayal', { by: 'alex', to: 'blake', kind: 'spare' }),
      ev('decisions', { decisions: [{ player: 'alex', label: 'good', regret: 1, best_delta: 2, actual_delta: 1 }] }),
      ev('commentary', { headline: 'BACKSTAB!', line: 'Ouch', hype: 1 }),
      ev('round_ended', { round: 1, coins: { ...coins, alex: 13, blake: 11 }, trust: { blake: { alex: -3 } } }),
    ]
    const v = reduceEvents(seats, 10, events)
    expect(v.maxRounds).toBe(5)
    expect(v.round).toBe(1)
    expect(v.phase).toBe('reveal')
    expect(v.players.alex.coins).toBe(13)
    expect(v.players.alex.lastDelta).toBe(1)
    expect(v.players.alex.speech?.text).toBe('Trust me!')
    expect(v.players.alex.decision?.label).toBe('good')
    expect(v.players.blake.mood).toBe('betrayed')
    expect(v.players.alex.thinking).toBe(false)
    expect(v.tags.r1.deception).toBe(0.9)
    expect(v.flights).toHaveLength(1)
    expect(v.effects.map((e) => e.kind)).toContain('betrayal')
    expect(v.trust.blake.alex).toBe(-3)
    expect(v.coinHistory).toHaveLength(2)
    expect(v.commentary?.headline).toBe('BACKSTAB!')
    const kinds = v.feed.map((f) => f.kind)
    expect(kinds).toEqual(expect.arrayContaining(['round', 'public', 'dm', 'move', 'betrayal', 'commentary']))
    expect(v.feed.find((f) => f.kind === 'dm')?.pledge?.kind).toBe('spare')
  })

  it('never mutates the previous view', () => {
    const before = initialView(seats)
    const frozen = JSON.stringify(before)
    applyEvent(before, ev('transfers', { transfers: [], deltas: {}, coins: { ...coins, alex: 99 } }))
    expect(JSON.stringify(before)).toBe(frozen)
  })

  it('ignores duplicate and out-of-order events', () => {
    const e = ev('transfers', { transfers: [], deltas: {}, coins: { ...coins, alex: 20 } })
    const once = applyEvent(initialView(seats), e)
    const twice = applyEvent(once, { ...e, data: { ...e.data, coins: { ...coins, alex: 1 } } })
    expect(twice.players.alex.coins).toBe(20)
  })

  it('handles eliminations, game over, report and errors', () => {
    const v = reduceEvents(seats, 10, [
      ev('eliminated', { player: 'drew' }),
      ev('game_over', { winners: ['alex'], coins, stats: {} }),
      ev('report', { headline: 'H', summary: 'S', awards: [], decisions: [], insights: [], generated_by: 'template' }),
    ])
    expect(v.players.drew.alive).toBe(false)
    expect(v.phase).toBe('over')
    expect(v.winners).toEqual(['alex'])
    expect(v.players.alex.mood).toBe('gleeful')
    expect(v.report?.headline).toBe('H')
    const err = applyEvent(v, ev('error', { message: 'boom' }))
    expect(err.phase).toBe('error')
    expect(err.error).toBe('boom')
  })

  it('records alliances, gang-ups, kept promises and lies in the feed', () => {
    const v = reduceEvents(seats, 10, [
      ev('alliance', { players: ['alex', 'blake'], mutual_gift: true }),
      ev('alliance', { players: ['charlie', 'drew'], mutual_gift: false }),
      ev('gang_up', { victim: 'drew', takers: ['alex', 'blake'] }),
      ev('promise_kept', { by: 'alex', to: 'blake', kind: 'give' }),
      ev('lie_detected', { by: 'charlie', to: 'drew', quote: 'trust me', explanation: 'lol no', severity: 'lie' }),
      ev('unknown_type', {}),
    ])
    expect(v.feed.map((f) => f.kind)).toEqual(['alliance', 'alliance', 'gang', 'kept', 'lie'])
    expect(v.feed[0].text).toMatch(/alliance bonus/)
    expect(v.effects).toHaveLength(4)
    expect(v.lastSeq).toBe(5)
  })

  it('caps the feed length', () => {
    let v = initialView(seats)
    for (let i = 0; i < MAX_FEED + 50; i++) v = applyEvent(v, ev('promise_kept', { by: 'alex', to: 'blake', kind: 'give' }))
    expect(v.feed).toHaveLength(MAX_FEED)
  })

  it('marks fallbacks from invalid model replies', () => {
    const v = reduceEvents(seats, 10, [
      ev('turn', { player: 'blake', subround: 1, mood: 'nervous', private_thought: '', public: null, dms: [], fallback: true }),
    ])
    expect(v.players.blake.fallbacks).toBe(1)
    expect(v.feed[0].text).toMatch(/froze/)
  })
})
