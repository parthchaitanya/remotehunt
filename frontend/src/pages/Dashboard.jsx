import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDateTime, timeAgo } from '../api.js'
import { Badge, Button, Card, Empty, EligibilityBadge, ErrorNote, ScoreBadge, Spinner, Stat, Toast, useLoad } from '../components/ui.jsx'

export default function Dashboard() {
  const { data, error, loading, reload } = useLoad(() => api.get('/dashboard'))
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState(false)

  const runSearch = async () => {
    setBusy(true)
    try {
      const r = await api.post('/search/run', {})
      setToast(r.started ? 'Search started – sources run in the background (rate limits respected).' : r.message)
    } catch (e) {
      setToast(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (loading && !data) return <Spinner />
  if (error) return <ErrorNote error={error} />
  const d = data
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Dashboard</h1>
          <p className="text-sm muted">Python Developer · Data Analyst · AI Engineer — remote-first, IST (UTC+5:30)</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={reload}>Refresh</Button>
          <Button variant="primary" busy={busy} onClick={runSearch}>Run search now</Button>
        </div>
      </div>

      {!d.resume && (
        <Card>
          <p className="text-sm">
            Start by <Link className="text-[var(--series-1)] underline" to="/resume">uploading your resume</Link> — match scores,
            tailoring and profile text all come from it.
          </p>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="ATS score" value={d.resume ? d.resume.ats_score : '—'} sub={d.resume ? `v${d.resume.version_no} · ${d.resume.grade}` : 'No resume'} />
        <Stat label="New jobs (24h)" value={d.new_jobs_24h} />
        <Stat label="High matches (7d)" value={d.high_match_7d} sub="eligible, not flagged" />
        <Stat label="Tracked" value={d.applications} />
        <Stat label="Interviews" value={d.interviews} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Top matches this week" className="lg:col-span-2" actions={<Link className="text-xs text-[var(--series-1)]" to="/jobs">All jobs →</Link>}>
          {d.top_jobs.length === 0 ? (
            <Empty>No jobs yet. Run a search, or wait for the next scheduled run.</Empty>
          ) : (
            <ul className="divide-y divide-[var(--grid)]">
              {d.top_jobs.map((j) => (
                <li key={j.id} className="flex items-start gap-3 py-2.5">
                  <ScoreBadge score={j.match_score} />
                  <div className="min-w-0 flex-1">
                    <Link to={`/jobs/${j.id}`} className="font-medium hover:underline">{j.title}</Link>
                    <div className="text-xs secondary">{j.company} · {j.location || j.remote_type} · {j.source}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <EligibilityBadge eligible={j.eligible} reason={j.eligibility_reason} />
                      <Badge>{j.apply_method_label}</Badge>
                      {j.tracker_status && <Badge tone="blue">{j.tracker_status}</Badge>}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-4">
          <Card title="Follow-ups due">
            {d.followups_due.length === 0 ? (
              <p className="text-sm muted">Nothing due. Applications get a reminder 7 days after you mark them applied.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {d.followups_due.map((f, i) => (
                  <li key={i}>
                    <span className="font-medium">{f.title || f.subject}</span>
                    {f.company && <span className="secondary"> – {f.company}</span>}
                    <div className="text-xs muted">{f.type === 'thread' ? 'No reply to your email for 7+ days' : `Applied ${timeAgo(f.applied_at)}`}</div>
                  </li>
                ))}
                <Link to="/tracker" className="text-xs text-[var(--series-1)]">Open tracker →</Link>
              </ul>
            )}
          </Card>

          <Card title="Notifications">
            {d.notifications.length === 0 ? (
              <p className="text-sm muted">No unread notifications.</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {d.notifications.map((n) => (
                  <li key={n.id} className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-medium">{n.title}</div>
                      <div className="text-xs secondary">{n.body}</div>
                    </div>
                    <button className="text-xs muted hover:underline" onClick={() => api.post(`/notifications/${n.id}/read`).then(reload)}>Dismiss</button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Status">
            <ul className="space-y-1 text-sm">
              <li>Gmail: {d.gmail_connected ? <Badge tone="green">● Connected</Badge> : <Link to="/settings"><Badge tone="amber">○ Not connected</Badge></Link>}</li>
              <li>Groq LLM: {d.llm_available ? <Badge tone="green">● Configured</Badge> : <Badge tone="amber">○ Rules-only mode</Badge>}</li>
            </ul>
            {d.scheduler.length > 0 && (
              <ul className="mt-3 space-y-0.5 text-xs muted">
                {d.scheduler.map((s) => <li key={s.id}>{s.id}: next {fmtDateTime(s.next_run)}</li>)}
              </ul>
            )}
          </Card>
        </div>
      </div>
      <Toast message={toast} onDone={() => setToast('')} />
    </div>
  )
}
