import { useEffect, useState } from 'react'

import { api, ApiError, streamUrl } from '../lib/api'
import { dwellFor } from '../lib/pacing'
import type { GameEvent } from '../lib/types'
import { useArena } from '../store/arena'

const MAX_RECONNECTS = 5

/** Load a game, then either stream it live over WebSocket or set it up for timed replay. */
export function useGameStream(gameId: string): { error: string | null } {
  const [failure, setFailure] = useState<{ gameId: string; message: string } | null>(null)

  useEffect(() => {
    const store = useArena.getState()
    store.reset()
    let socket: WebSocket | null = null
    let cancelled = false
    let attempts = 0
    let retryTimer: number | undefined
    const setError = (message: string) => setFailure({ gameId, message })

    const connect = () => {
      store.setConnection('connecting')
      socket = new WebSocket(streamUrl(gameId))
      socket.onopen = () => { attempts = 0; useArena.getState().setConnection('open') }
      socket.onmessage = (msg) => {
        const data = JSON.parse(msg.data as string) as GameEvent | { type: 'stream_end' }
        if (data.type === 'stream_end') {
          useArena.getState().setConnection('closed')
          socket?.close()
          return
        }
        useArena.getState().receive(data as GameEvent)
      }
      socket.onclose = (e) => {
        if (cancelled || useArena.getState().connection === 'closed') return
        if (e.code === 4404) { setError('We could not find that game.'); return }
        if (attempts++ < MAX_RECONNECTS) {
          useArena.getState().setConnection('connecting')
          retryTimer = window.setTimeout(connect, 1000 * attempts)
        } else {
          useArena.getState().setConnection('error')
        }
      }
    }

    api.game(gameId)
      .then((detail) => {
        if (cancelled) return
        useArena.getState().hydrate(detail.game, detail.events, detail.live)
        if (detail.live) connect()
      })
      .catch((e: unknown) => !cancelled && setError(e instanceof ApiError ? e.message : 'Something went wrong.'))

    return () => {
      cancelled = true
      window.clearTimeout(retryTimer)
      socket?.close()
    }
  }, [gameId])

  return { error: failure?.gameId === gameId ? failure.message : null }
}

/** Drives replay playback: applies the next event after a dwell time that matches its drama. */
export function useReplayClock(): void {
  const mode = useArena((s) => s.mode)
  const playing = useArena((s) => s.playing)
  const cursor = useArena((s) => s.cursor)
  const speed = useArena((s) => s.speed)
  const total = useArena((s) => s.events.length)

  useEffect(() => {
    if (mode !== 'replay' || !playing) return
    if (cursor >= total) { useArena.setState({ playing: false }); return }
    const prev = cursor > 0 ? useArena.getState().events[cursor - 1].type : 'game_started'
    const timer = window.setTimeout(() => useArena.getState().step(), cursor === 0 ? 300 : dwellFor(prev, speed))
    return () => window.clearTimeout(timer)
  }, [mode, playing, cursor, speed, total])
}
