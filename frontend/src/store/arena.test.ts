import { dwellFor } from '../lib/pacing'
import type { GameEvent, GameRecord } from '../lib/types'
import { useArena } from './arena'

const record: GameRecord = {
  id: 'g1', status: 'finished', created_at: 0, finished_at: 1, backend: 'fake',
  config: { max_rounds: 3, starting_coins: 12, negotiation_subrounds: 2, seed: 1 },
  seats: [
    { player_id: 'alex', name: 'Alex', model_key: 'a', display_name: 'A', lab: 'L', color: '#fff', emoji: 'x', reasoning: 'none', provider: 'fake' },
    { player_id: 'blake', name: 'Blake', model_key: 'b', display_name: 'B', lab: 'L', color: '#000', emoji: 'y', reasoning: 'none', provider: 'fake' },
  ],
  winners: [], final_coins: {}, player_stats: {}, cost_usd: 0, headline: null, error: null,
}

const transfer = (seq: number, alex: number): GameEvent => ({
  game_id: 'g1', seq, type: 'transfers', round: 1, ts: seq,
  data: { transfers: [], deltas: {}, coins: { alex, blake: 12 } },
})

beforeEach(() => useArena.getState().reset())

describe('arena store', () => {
  it('replays from the start and steps forward', () => {
    useArena.getState().hydrate(record, [transfer(1, 14), transfer(0, 13)], false)
    let s = useArena.getState()
    expect(s.mode).toBe('replay')
    expect(s.playing).toBe(true)
    expect(s.cursor).toBe(0)
    expect(s.events.map((e) => e.seq)).toEqual([0, 1])
    s.step()
    expect(useArena.getState().view.players.alex.coins).toBe(13)
    useArena.getState().step()
    useArena.getState().step() // past the end -> stops playing
    s = useArena.getState()
    expect(s.view.players.alex.coins).toBe(14)
    expect(s.playing).toBe(false)
  })

  it('seeks backwards by re-reducing a prefix', () => {
    useArena.getState().hydrate(record, [transfer(0, 13), transfer(1, 14)], false)
    useArena.getState().seek(99)
    expect(useArena.getState().view.players.alex.coins).toBe(14)
    useArena.getState().seek(1)
    expect(useArena.getState().view.players.alex.coins).toBe(13)
  })

  it('applies live events immediately and dedupes the backlog', () => {
    useArena.getState().hydrate({ ...record, status: 'running' }, [transfer(0, 13)], true)
    useArena.getState().receive(transfer(0, 13))
    useArena.getState().receive(transfer(1, 15))
    const s = useArena.getState()
    expect(s.events).toHaveLength(2)
    expect(s.cursor).toBe(2)
    expect(s.view.players.alex.coins).toBe(15)
  })

  it('restarts a finished replay when play is pressed', () => {
    useArena.getState().hydrate(record, [transfer(0, 13)], false)
    useArena.getState().seek(1)
    useArena.setState({ playing: false })
    useArena.getState().togglePlay()
    expect(useArena.getState().cursor).toBe(0)
    expect(useArena.getState().playing).toBe(true)
  })

  it('scales dwell time by speed', () => {
    expect(dwellFor('commentary', 1)).toBeGreaterThan(dwellFor('commentary', 4))
    expect(dwellFor('mystery')).toBe(500)
  })
})

describe('arena store gap repair', () => {
  it('rebuilds the view when a missed older event arrives late', () => {
    useArena.getState().hydrate({ ...record, status: 'running' }, [transfer(0, 13), transfer(2, 15)], true)
    expect(useArena.getState().view.players.alex.coins).toBe(15)
    useArena.getState().receive({ ...transfer(1, 14), type: 'promise_kept', data: { by: 'alex', to: 'blake', kind: 'give' } })
    const s = useArena.getState()
    expect(s.events.map((e) => e.seq)).toEqual([0, 1, 2])
    expect(s.view.feed.some((f) => f.kind === 'kept')).toBe(true)
    expect(s.view.players.alex.coins).toBe(15)
  })
})
