import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { api } from './api.js'
import { Spinner } from './components/ui.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Login from './pages/Login.jsx'
import Documents from './pages/Documents.jsx'
import Jobs from './pages/Jobs.jsx'
import Profiles from './pages/Profiles.jsx'
import Resume from './pages/Resume.jsx'
import Settings from './pages/Settings.jsx'
import Sources from './pages/Sources.jsx'
import Stats from './pages/Stats.jsx'
import Tracker from './pages/Tracker.jsx'

const NAV = [
  ['/', 'Dashboard', '◧'],
  ['/jobs', 'Jobs', '☰'],
  ['/tracker', 'Tracker', '▦'],
  ['/documents', 'Documents', '✎'],
  ['/resume', 'Resume', '▤'],
  ['/profiles', 'Profiles', '◉'],
  ['/sources', 'Sources', '⇄'],
  ['/stats', 'Stats', '▮'],
  ['/settings', 'Settings & Gmail', '⚙'],
]

export default function App() {
  const [auth, setAuth] = useState(null) // null = checking
  const check = () => api.get('/auth/me').then(setAuth).catch(() => setAuth({ authenticated: false, auth_enabled: true }))
  useEffect(() => {
    check()
    const onUnauthorized = () => setAuth((a) => ({ ...(a || {}), authenticated: false, auth_enabled: true }))
    window.addEventListener('rh:unauthorized', onUnauthorized)
    return () => window.removeEventListener('rh:unauthorized', onUnauthorized)
  }, [])

  if (auth === null) return <div className="flex min-h-screen items-center justify-center"><Spinner /></div>
  if (!auth.authenticated) return <Login onDone={check} />
  return <Shell authEnabled={auth.auth_enabled} demo={auth.demo} onLogout={() => api.post('/auth/logout').then(check)} />
}

function DemoBanner() {
  return (
    <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-200">
      <b>Live demo</b> with a fictional candidate and a snapshot of real public job postings. Gmail, live searches and
      uploads are disabled here.{' '}
      <a className="underline" href="https://github.com/parthchaitanya/remotehunt" target="_blank" rel="noreferrer">Run your own copy →</a>
    </div>
  )
}

function Shell({ authEnabled, demo, onLogout }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="min-h-screen md:flex">
      <header className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3 md:hidden">
        <span className="font-semibold">RemoteHunt</span>
        <button className="rounded px-2 py-1 text-sm" onClick={() => setOpen((o) => !o)} aria-label="Menu">☰</button>
      </header>
      <nav
        className={`${open ? 'block' : 'hidden'} border-r border-[var(--border)] bg-[var(--surface-1)] p-3 md:sticky md:top-0 md:block md:h-screen md:w-56 md:shrink-0`}
      >
        <div className="mb-4 hidden items-center gap-2 px-2 md:flex">
          <img src="/favicon.svg" alt="" className="h-7 w-7" />
          <span className="text-lg font-semibold">RemoteHunt</span>
        </div>
        <ul className="space-y-0.5">
          {NAV.map(([to, label, icon]) => (
            <li key={to}>
              <NavLink
                to={to}
                end={to === '/'}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${isActive ? 'bg-[var(--series-1)] text-white' : 'secondary hover:bg-black/5 dark:hover:bg-white/5'}`
                }
              >
                <span className="w-4 text-center" aria-hidden>{icon}</span>
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
        {authEnabled && (
          <button onClick={onLogout} className="mt-3 w-full rounded-lg px-2 py-1.5 text-left text-sm secondary hover:bg-black/5 dark:hover:bg-white/5">
            ⎋ Sign out
          </button>
        )}
        <p className="mt-6 px-2 text-[11px] leading-snug muted">
          Nothing is applied for or sent without your approval. Recruiter replies are saved as Gmail drafts only.
        </p>
      </nav>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-5 md:px-6">
        {demo && <DemoBanner />}
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<Jobs />} />
          <Route path="/tracker" element={<Tracker />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/resume" element={<Resume />} />
          <Route path="/profiles" element={<Profiles />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
