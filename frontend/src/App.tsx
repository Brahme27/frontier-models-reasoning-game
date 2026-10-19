import { lazy, Suspense } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'

import { ErrorPanel, Spinner } from './components/ui'
import Lobby from './pages/Lobby'

const Arena = lazy(() => import('./pages/Arena'))
const Leaderboard = lazy(() => import('./pages/Leaderboard'))
const Learn = lazy(() => import('./pages/Learn'))

const NAV = [
  { to: '/', label: 'Lobby' },
  { to: '/leaderboard', label: 'Leaderboard' },
  { to: '/learn', label: 'Learn' },
]

export default function App() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-gold focus:px-3 focus:py-2 focus:text-ink">
        Skip to content
      </a>
      <header className="sticky top-0 z-40 border-b border-line/60 bg-ink/80 backdrop-blur-md">
        <nav className="mx-auto flex max-w-[1600px] items-center gap-2 px-4 py-3 sm:px-6" aria-label="Main">
          <NavLink to="/" className="mr-auto font-display text-base text-pink neon-text sm:text-xl">OUTSMART</NavLink>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === '/'}
              className={({ isActive }) => `min-h-11 rounded-full px-2 py-2.5 font-mono text-[10px] tracking-wider uppercase transition-colors sm:px-4 sm:text-xs
                ${isActive ? 'bg-white/10 text-gold' : 'text-dust hover:text-chalk'}`}>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main id="main" className="flex-1">
        <Suspense fallback={<div className="grid min-h-[50vh] place-items-center"><Spinner /></div>}>
          <Routes>
            <Route path="/" element={<Lobby />} />
            <Route path="/games/:gameId" element={<Arena />} />
            <Route path="/leaderboard" element={<Leaderboard />} />
            <Route path="/learn" element={<Learn />} />
            <Route path="*" element={<div className="px-4 py-24"><ErrorPanel title="Wrong table" message="This page doesn't exist. The game is in the lobby." /></div>} />
          </Routes>
        </Suspense>
      </main>
      <footer className="border-t border-line/60 px-4 py-6 text-center font-mono text-[11px] text-dust">
        Open-weight players from OpenAI · Google · Mistral · Alibaba, judged by a neutral DeepSeek analyst. Built with FastAPI, React and AWS.
      </footer>
    </div>
  )
}
