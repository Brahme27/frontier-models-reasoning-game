import type { GameView } from '../../lib/reducer'

function cellColor(score: number): string {
  if (score === 0) return 'rgb(255 255 255 / 0.04)'
  const strength = Math.min(1, Math.abs(score) / 5)
  return score > 0
    ? `color-mix(in srgb, var(--color-lime) ${20 + strength * 60}%, transparent)`
    : `color-mix(in srgb, var(--color-pink) ${20 + strength * 60}%, transparent)`
}

export function TrustMatrix({ view }: { view: GameView }) {
  const ids = view.order
  return (
    <div className="p-4">
      <p className="mb-3 text-xs text-dust">
        How much each player (row) <em>trusts</em> each rival (column). Gifts and kept promises build trust; thefts and betrayals destroy it.
      </p>
      <div className="grid gap-1" style={{ gridTemplateColumns: `4.5rem repeat(${ids.length}, minmax(0, 1fr))` }} role="table" aria-label="Trust matrix">
        <span />
        {ids.map((id) => (
          <span key={id} role="columnheader" className="truncate text-center font-display text-[10px]" style={{ color: view.players[id]?.color }}>
            {view.players[id]?.name}
          </span>
        ))}
        {ids.map((row) => (
          <div key={row} role="row" className="contents">
            <span role="rowheader" className="self-center truncate font-display text-[10px]" style={{ color: view.players[row]?.color }}>
              {view.players[row]?.name}
            </span>
            {ids.map((col) => {
              const score = view.trust[row]?.[col] ?? 0
              return (
                <span key={col} role="cell"
                  className="grid aspect-square place-items-center rounded-md font-mono text-xs text-chalk transition-colors duration-700"
                  style={{ background: row === col ? 'transparent' : cellColor(score) }}
                  title={row === col ? '' : `${view.players[row]?.name} → ${view.players[col]?.name}: ${score}`}>
                  {row === col ? '·' : score > 0 ? `+${score}` : score}
                </span>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
