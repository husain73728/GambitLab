import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { api, type Account } from '../api'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/games', label: 'My Games' },
  { to: '/openings', label: 'Openings' },
  { to: '/tactics', label: 'Tactics' },
  { to: '/clock', label: 'Clock' },
  { to: '/training', label: 'Training' },
  { to: '/progress', label: 'Progress' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  const [account, setAccount] = useState<Account | null>(null)
  const [loaded, setLoaded] = useState(false)
  const location = useLocation()

  useEffect(() => {
    api.me().then((r) => setAccount(r.account)).catch(() => setAccount(null)).finally(() => setLoaded(true))
  }, [location.pathname])

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-20 border-b backdrop-blur" style={{ borderColor: 'var(--line)', background: 'rgba(11,16,32,0.82)' }}>
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="text-xl font-black tracking-tight">
              <span style={{ color: 'var(--accent)' }}>Gambit</span>Lab
            </span>
          </NavLink>
          <span className="hidden text-xs muted sm:inline">your chess improvement lab</span>
          <nav className="ml-auto flex flex-wrap items-center gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                className={({ isActive }) =>
                  `rounded-lg px-2.5 py-1.5 text-sm ${isActive ? 'bg-[#223055] text-white' : 'muted hover:text-white'}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          {loaded && (
            <NavLink to="/onboarding" className="chip" title="Connected account">
              {account ? `♟ ${account.username}` : '＋ connect chess.com'}
            </NavLink>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-8 pt-2 text-xs muted">
        Personal analysis tool. Chess.com data via the public API; engine analysis is computed locally.
        Not affiliated with Chess.com.
      </footer>
    </div>
  )
}
