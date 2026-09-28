import { useState } from 'react'
import { api, fmtDateTime, timeAgo } from '../api.js'
import { Button, Card, ErrorNote, HealthBadge, Spinner, Toast, useLoad } from '../components/ui.jsx'

function limitText(l) {
  const parts = []
  if (l.max_calls_per_day) parts.push(`${l.max_calls_per_day}/day`)
  if (l.max_calls_per_week) parts.push(`${l.max_calls_per_week}/week`)
  if (l.lifetime_budget) parts.push(`${l.lifetime_budget} lifetime`)
  if (l.min_hours_between_runs) parts.push(`every ≥${l.min_hours_between_runs}h`)
  return parts.join(' · ') || 'no limit set'
}

export default function Sources() {
  const { data, error, loading, reload } = useLoad(() => api.get('/sources'))
  const [busy, setBusy] = useState('')
  const [toast, setToast] = useState('')
  const [open, setOpen] = useState(null)

  const act = async (key, fn, msg) => {
    setBusy(key)
    try { await fn(); setToast(msg); reload() } catch (e) { setToast(e.message) } finally { setBusy('') }
  }

  if (loading && !data) return <Spinner />
  if (error) return <ErrorNote error={error} />
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Sources & health</h1>
          <p className="text-sm muted">Official APIs, RSS feeds and your own Gmail only. Budgets are enforced before every call; a failing source is logged and skipped.</p>
        </div>
        <div className="flex gap-2">
          <Button busy={busy === 'health'} onClick={() => act('health', () => api.post('/sources/health-check'), 'Health checks done')}>Run health checks</Button>
          <Button variant="primary" busy={busy === 'run'} disabled={data.running}
            onClick={() => act('run', () => api.post('/search/run', {}), 'Search started (due sources only)')}>
            {data.running ? 'Search running…' : 'Run due sources'}
          </Button>
        </div>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs muted">
              <th className="p-3">Source</th><th>Status</th><th>Last run</th><th className="text-right">Last fetch</th><th className="pl-3">Budget used (24h / 7d / all)</th><th>Limits</th><th />
            </tr>
          </thead>
          <tbody>
            {data.sources.map((s) => (
              <tr key={s.name} className="border-b border-[var(--grid)] align-top">
                <td className="p-3">
                  <div className="font-medium">{s.name}</div>
                  <div className="text-xs muted">{s.type}{!s.enabled && ' · disabled'}</div>
                </td>
                <td className="py-3">
                  <HealthBadge status={s.enabled ? (s.configured ? s.status : 'unconfigured') : 'disabled'} />
                  <div className="mt-1 max-w-56 text-xs secondary">{s.configured ? s.message : s.config_message}</div>
                  {s.consecutive_failures > 0 && <div className="text-xs text-red-700 dark:text-red-300">{s.consecutive_failures} consecutive failure(s)</div>}
                </td>
                <td className="py-3 text-xs secondary" title={fmtDateTime(s.last_run_at)}>{timeAgo(s.last_run_at)}</td>
                <td className="py-3 text-right tabular-nums">{s.last_fetch_count}</td>
                <td className="py-3 pl-3 text-xs tabular-nums secondary">
                  {s.usage.last_24h} / {s.usage.last_7d} / {s.usage.lifetime}
                  {s.remaining !== null && <div className="muted">{s.remaining} calls left now</div>}
                </td>
                <td className="py-3 text-xs secondary">{limitText(s.limits)}</td>
                <td className="py-3 pr-3 text-right">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" busy={busy === s.name} onClick={() => act(s.name, () => api.post(`/sources/${s.name}/health-check`), `${s.name}: checked`)}>Check</Button>
                    <Button variant="ghost" onClick={() => setOpen(open === s.name ? null : s.name)}>{open === s.name ? 'Hide' : 'Runs'}</Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && (() => {
        const s = data.sources.find((x) => x.name === open)
        return (
          <Card title={`${s.name}: recent runs`}>
            {s.recent_runs.length === 0 ? <p className="text-sm muted">No runs yet.</p> : (
              <ul className="space-y-1 text-sm">
                {s.recent_runs.map((r, i) => (
                  <li key={i}>{fmtDateTime(r.started_at)} — <b>{r.status}</b> · fetched {r.fetched}, new {r.new} {r.error && <span className="text-xs text-red-700 dark:text-red-300">({r.error})</span>}</li>
                ))}
              </ul>
            )}
            {s.details?.companies && (
              <div className="mt-3">
                <div className="text-xs font-medium">Company boards</div>
                <ul className="mt-1 grid gap-0.5 text-xs sm:grid-cols-2">
                  {Object.entries(s.details.companies).map(([c, st]) => <li key={c}><span className="font-mono">{c}</span>: <span className={st.startsWith('ok') ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}>{st}</span></li>)}
                </ul>
              </div>
            )}
          </Card>
        )
      })()}
      <Card title="Target companies (config/target_companies.yaml)">
        <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
          {Object.entries(data.target_companies).map(([platform, list]) => (
            <div key={platform}>
              <div className="text-xs font-semibold uppercase muted">{platform}</div>
              <ul className="secondary">{(list || []).map((c) => <li key={c.token}>{c.name}</li>)}</ul>
            </div>
          ))}
        </div>
      </Card>
      <Toast message={toast} onDone={() => setToast('')} />
    </div>
  )
}
