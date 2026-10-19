import { AnimatePresence, motion } from 'motion/react'
import { Lock } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { MOOD_EMOJI } from '../../lib/moods'
import { nameOf, type FeedItem, type FeedKind, type GameView } from '../../lib/reducer'

type Filter = 'all' | 'talk' | 'drama'

const FILTERS: Record<Filter, (k: FeedKind) => boolean> = {
  all: () => true,
  talk: (k) => k === 'public' || k === 'dm',
  drama: (k) => ['betrayal', 'alliance', 'gang', 'lie', 'eliminated', 'commentary', 'move'].includes(k),
}

const PLEDGE_TEXT = { give: 'pledge: give', spare: 'pledge: spare', attack: 'pledge: attack' } as const

const KIND_STYLE: Partial<Record<FeedKind, { icon: string; color: string }>> = {
  betrayal: { icon: '🗡️', color: 'var(--color-pink)' },
  alliance: { icon: '🤝', color: 'var(--color-lime)' },
  gang: { icon: '👊', color: 'var(--color-amber)' },
  kept: { icon: '✅', color: 'var(--color-lime)' },
  lie: { icon: '🤥', color: 'var(--color-pink)' },
  eliminated: { icon: '💀', color: 'var(--color-pink)' },
  commentary: { icon: '🎙️', color: 'var(--color-gold)' },
  system: { icon: '📺', color: 'var(--color-dust)' },
}

function Row({ item, view }: { item: FeedItem; view: GameView }) {
  const from = item.from ? view.players[item.from] : undefined
  const color = from?.color ?? 'var(--color-dust)'
  const tag = item.ref ? view.tags[item.ref] : undefined

  if (item.kind === 'round') {
    return (
      <div className="flex items-center gap-3 py-2">
        <span className="h-px flex-1 bg-line" />
        <span className="font-display text-xs tracking-widest text-gold">{item.text}</span>
        <span className="h-px flex-1 bg-line" />
      </div>
    )
  }

  if (item.kind === 'public' || item.kind === 'dm') {
    const isDm = item.kind === 'dm'
    return (
      <div className={`rounded-xl px-3 py-2 ${isDm ? 'border border-dashed border-line bg-white/[0.02]' : 'bg-white/[0.04]'}`}>
        <p className="flex items-center gap-1.5 text-xs">
          <span className="font-display tracking-wide" style={{ color }}>{from?.name}</span>
          {isDm && (
            <>
              <span className="text-dust">→</span>
              <span className="font-display tracking-wide" style={{ color: view.players[item.to ?? '']?.color }}>{nameOf(view, item.to)}</span>
              <Lock size={11} className="text-dust" aria-label="private message" />
            </>
          )}
          {tag && <span className="ml-auto" title={`${tag.emotion}: ${tag.tone}`}>{MOOD_EMOJI[tag.emotion]}</span>}
        </p>
        <p className="mt-1 text-sm leading-snug text-chalk">{item.text}</p>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {item.pledge && (
            <span className="rounded bg-cyan/10 px-1.5 py-0.5 font-mono text-[10px] text-cyan uppercase">
              {PLEDGE_TEXT[item.pledge.kind]}{item.pledge.target ? ` → ${nameOf(view, item.pledge.target)}` : ''}
            </span>
          )}
          {tag && (
            <span className="flex items-center gap-1 font-mono text-[10px] text-dust" title="Deception likelihood (AI lie detector)">
              🕵
              <span className="relative h-1.5 w-14 overflow-hidden rounded-full bg-white/10">
                <span className="absolute inset-y-0 left-0 rounded-full"
                  style={{ width: `${tag.deception * 100}%`, background: tag.deception > 0.5 ? 'var(--color-pink)' : 'var(--color-lime)' }} />
              </span>
              {Math.round(tag.deception * 100)}%
            </span>
          )}
        </div>
      </div>
    )
  }

  if (item.kind === 'move') {
    return (
      <div className="rounded-xl border px-3 py-2" style={{ borderColor: `${color}55` }}>
        <p className="text-sm"><span className="font-display text-xs tracking-wide" style={{ color }}>{from?.name}</span> <span className="text-chalk">{item.text}</span></p>
        {item.meta && <p className="mt-0.5 text-xs text-dust italic">“{item.meta}”</p>}
      </div>
    )
  }

  const style = KIND_STYLE[item.kind] ?? KIND_STYLE.system!
  return (
    <div className="flex gap-2 rounded-xl px-3 py-2" style={{ background: `color-mix(in srgb, ${style.color} 9%, transparent)` }}>
      <span aria-hidden>{style.icon}</span>
      <div className="text-sm leading-snug" style={{ color: style.color }}>
        {item.kind === 'commentary' && item.meta && <span className="mr-1 font-display text-xs">{item.meta}</span>}
        {item.text}
        {item.kind === 'lie' && item.meta && <span className="mt-0.5 block text-xs text-dust italic">said: “{item.meta}”</span>}
      </div>
    </div>
  )
}

export function Feed({ view }: { view: GameView }) {
  const [filter, setFilter] = useState<Filter>('all')
  const [stick, setStick] = useState(true)
  const ref = useRef<HTMLDivElement>(null)
  const items = useMemo(() => view.feed.filter((f) => f.kind === 'round' || FILTERS[filter](f.kind)), [view.feed, filter])

  useEffect(() => {
    if (stick && ref.current) ref.current.scrollTo({ top: ref.current.scrollHeight, behavior: 'smooth' })
  }, [items.length, stick])

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex gap-1 p-2" role="tablist" aria-label="Feed filter">
        {(Object.keys(FILTERS) as Filter[]).map((f) => (
          <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
            className={`min-h-9 rounded-full px-3 font-mono text-[11px] tracking-wider uppercase transition-colors
              ${filter === f ? 'bg-pink text-ink' : 'text-dust hover:bg-white/5 hover:text-chalk'}`}>
            {f}
          </button>
        ))}
      </div>
      <div ref={ref} className="scrollbar-thin min-h-0 flex-1 space-y-2 overflow-y-auto px-3 pb-3"
        onScroll={(e) => {
          const el = e.currentTarget
          setStick(el.scrollHeight - el.scrollTop - el.clientHeight < 60)
        }}>
        {items.length === 0 && <p className="py-10 text-center text-sm text-dust">The table is quiet… for now.</p>}
        <AnimatePresence initial={false}>
          {items.map((item) => (
            <motion.div key={item.id} layout="position" initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }}>
              <Row item={item} view={view} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
