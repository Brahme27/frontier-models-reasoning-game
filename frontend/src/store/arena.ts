import { create } from 'zustand'

import { applyEvent, initialView, reduceEvents, type GameView } from '../lib/reducer'
import type { Speed } from '../lib/pacing'
import type { GameEvent, GameRecord } from '../lib/types'

export type Mode = 'live' | 'replay'
export type Connection = 'idle' | 'connecting' | 'open' | 'closed' | 'error'

interface ArenaState {
  gameId: string | null
  record: GameRecord | null
  events: GameEvent[]
  cursor: number // number of events applied to `view`
  view: GameView
  mode: Mode
  playing: boolean
  speed: Speed
  connection: Connection
  hydrate: (record: GameRecord, events: GameEvent[], live: boolean) => void
  receive: (event: GameEvent) => void
  step: () => void
  seek: (cursor: number) => void
  togglePlay: () => void
  setSpeed: (speed: Speed) => void
  setConnection: (connection: Connection) => void
  reset: () => void
}

const viewFor = (record: GameRecord | null, events: GameEvent[]): GameView =>
  record ? reduceEvents(record.seats, record.config.max_rounds, events) : initialView()

export const useArena = create<ArenaState>((set, get) => ({
  gameId: null,
  record: null,
  events: [],
  cursor: 0,
  view: initialView(),
  mode: 'live',
  playing: false,
  speed: 1,
  connection: 'idle',

  hydrate: (record, events, live) => {
    const sorted = [...events].sort((a, b) => a.seq - b.seq)
    const cursor = live ? sorted.length : 0
    set({
      gameId: record.id, record, events: sorted, cursor,
      view: viewFor(record, sorted.slice(0, cursor)),
      mode: live ? 'live' : 'replay', playing: !live,
    })
  },

  receive: (event) => {
    const { events, cursor, view, mode } = get()
    if (events.some((e) => e.seq === event.seq)) return
    const next = [...events, event].sort((a, b) => a.seq - b.seq)
    const following = mode === 'live' && cursor === events.length
    if (following && event.seq > view.lastSeq) {
      set({ events: next, cursor: next.length, view: applyEvent(view, event) })
    } else if (following) {
      // a gap was filled (e.g. resent after a reconnect): rebuild so nothing is skipped
      set({ events: next, cursor: next.length, view: viewFor(get().record, next) })
    } else {
      set({ events: next })
    }
  },

  step: () => {
    const { events, cursor, view } = get()
    if (cursor >= events.length) {
      set({ playing: false })
      return
    }
    set({ cursor: cursor + 1, view: applyEvent(view, events[cursor]) })
  },

  seek: (target) => {
    const { events, record } = get()
    const cursor = Math.max(0, Math.min(events.length, target))
    set({ cursor, view: viewFor(record, events.slice(0, cursor)) })
  },

  togglePlay: () => {
    const { playing, cursor, events } = get()
    if (!playing && cursor >= events.length) get().seek(0)
    set({ playing: !playing })
  },

  setSpeed: (speed) => set({ speed }),
  setConnection: (connection) => set({ connection }),
  reset: () => set({
    gameId: null, record: null, events: [], cursor: 0, view: initialView(),
    mode: 'live', playing: false, connection: 'idle',
  }),
}))
