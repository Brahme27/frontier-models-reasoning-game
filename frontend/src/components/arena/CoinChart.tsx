import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import type { GameView } from '../../lib/reducer'

export function CoinChart({ view }: { view: GameView }) {
  const data = view.coinHistory.map((coins, round) => ({ round, ...coins }))
  if (data.length < 2) {
    return <p className="p-6 text-center text-sm text-dust">The coin race chart appears after round 1.</p>
  }
  return (
    <div className="h-64 p-3" role="img" aria-label="Coins per player over rounds">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="rgb(255 255 255 / 0.06)" vertical={false} />
          <XAxis dataKey="round" stroke="var(--color-dust)" tick={{ fontSize: 11, fontFamily: 'IBM Plex Mono' }} />
          <YAxis stroke="var(--color-dust)" allowDecimals={false} tick={{ fontSize: 11, fontFamily: 'IBM Plex Mono' }} />
          <Tooltip contentStyle={{ background: 'var(--color-night)', border: '1px solid var(--color-line)', borderRadius: 12, fontSize: 12 }}
            labelFormatter={(r) => `After round ${r}`} />
          {view.order.map((id) => (
            <Line key={id} type="monotone" dataKey={id} name={view.players[id]?.name} stroke={view.players[id]?.color}
              strokeWidth={2.5} dot={{ r: 2.5 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
