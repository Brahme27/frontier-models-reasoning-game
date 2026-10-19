import { Pause, Play, SkipForward, StepForward } from 'lucide-react'

import { SPEEDS } from '../../lib/pacing'
import { useArena } from '../../store/arena'

export function ReplayBar() {
  const { cursor, events, playing, speed, togglePlay, step, seek, setSpeed } = useArena()
  const total = events.length
  return (
    <div className="panel flex flex-wrap items-center gap-3 rounded-2xl px-3 py-2">
      <button onClick={togglePlay} aria-label={playing ? 'Pause replay' : 'Play replay'}
        className="grid h-11 w-11 place-items-center rounded-full bg-gold text-ink transition-transform active:scale-90">
        {playing ? <Pause size={18} /> : <Play size={18} />}
      </button>
      <button onClick={step} aria-label="Next event" disabled={cursor >= total}
        className="grid h-11 w-11 place-items-center rounded-full text-dust hover:bg-white/5 hover:text-chalk disabled:opacity-30">
        <StepForward size={18} />
      </button>
      <input type="range" min={0} max={total} value={cursor} onChange={(e) => seek(Number(e.target.value))}
        aria-label="Replay position" className="h-2 min-w-32 flex-1 cursor-pointer accent-[var(--color-gold)]" />
      <span className="font-mono text-xs text-dust tabular-nums">{cursor}/{total}</span>
      <div className="flex rounded-full bg-white/5 p-0.5" role="group" aria-label="Replay speed">
        {SPEEDS.map((s) => (
          <button key={s} onClick={() => setSpeed(s)} aria-pressed={speed === s}
            className={`min-h-9 rounded-full px-2.5 font-mono text-xs ${speed === s ? 'bg-cyan text-ink' : 'text-dust hover:text-chalk'}`}>
            {s}×
          </button>
        ))}
      </div>
      <button onClick={() => seek(total)} aria-label="Skip to the end"
        className="grid h-11 w-11 place-items-center rounded-full text-dust hover:bg-white/5 hover:text-chalk">
        <SkipForward size={18} />
      </button>
    </div>
  )
}
