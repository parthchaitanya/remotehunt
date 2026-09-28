import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDate, timeAgo } from '../api.js'
import { Badge, Button, Card, ErrorNote, ScoreBadge, Spinner, Toast, useLoad } from '../components/ui.jsx'

const LABELS = { saved: 'Saved', applying: 'Applying', applied: 'Applied', interview: 'Interview', offer: 'Offer', rejected: 'Rejected', withdrawn: 'Withdrawn' }

export default function Tracker() {
  const board = useLoad(() => api.get('/tracker'))
  const follow = useLoad(() => api.get('/tracker/followups'))
  const [dragId, setDragId] = useState(null)
  const [over, setOver] = useState(null)
  const [toast, setToast] = useState('')
  const [draft, setDraft] = useState(null)

  const move = async (appId, status) => {
    try {
      await api.patch(`/tracker/${appId}`, { status })
      if (status === 'applied') setToast('Marked applied – a follow-up reminder is set for 7 days from now.')
      board.reload()
      follow.reload()
    } catch (e) {
      setToast(e.message)
    }
  }

  const followUp = async (appId) => {
    try {
      const r = await api.post(`/tracker/${appId}/followup-draft`)
      setDraft(r)
    } catch (e) {
      setToast(e.message)
    }
  }

  if (board.loading && !board.data) return <Spinner />
  if (board.error) return <ErrorNote error={board.error} />
  const { statuses, columns } = board.data
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Application tracker</h1>
        <p className="text-sm muted">Drag cards between columns (or use the menu on each card). You apply yourself — RemoteHunt never auto-applies.</p>
      </div>

      {follow.data?.length > 0 && (
        <Card title={`Follow-ups due (${follow.data.length})`}>
          <ul className="space-y-2 text-sm">
            {follow.data.map((f, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  <span className="font-medium">{f.title || f.subject}</span> {f.company && <span className="secondary">– {f.company}</span>}
                  <span className="ml-2 text-xs muted">{f.type === 'thread' ? `waiting since ${fmtDate(f.waiting_since)}` : `applied ${timeAgo(f.applied_at)}`}</span>
                </span>
                <span className="flex gap-1.5">
                  {f.type === 'application' && <Button onClick={() => followUp(f.application_id)}>Draft follow-up</Button>}
                  {f.type === 'application' && <Button variant="ghost" onClick={() => api.patch(`/tracker/${f.application_id}`, { follow_up_done: true }).then(follow.reload)}>Done</Button>}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {draft && (
        <Card title="Follow-up draft" actions={<Button variant="ghost" onClick={() => setDraft(null)}>Close</Button>}>
          <p className="mb-2 text-xs muted">
            {draft.draft_id ? <>Saved as a Gmail draft (not sent). <a className="underline" href={draft.open_url} target="_blank" rel="noreferrer">Open drafts ↗</a></> : draft.note || 'No related email thread found – copy this into your email client.'}
          </p>
          <pre className="prose-pre rounded-lg bg-black/[.03] p-3 text-sm dark:bg-white/5">{draft.body}</pre>
        </Card>
      )}

      <div className="flex gap-3 overflow-x-auto pb-3">
        {statuses.map((s) => (
          <div
            key={s}
            onDragOver={(e) => { e.preventDefault(); setOver(s) }}
            onDragLeave={() => setOver(null)}
            onDrop={(e) => { e.preventDefault(); setOver(null); if (dragId) move(dragId, s); setDragId(null) }}
            className={`w-64 shrink-0 rounded-xl border p-2 transition ${over === s ? 'border-[var(--series-1)] bg-blue-50/50 dark:bg-blue-950/30' : 'border-[var(--border)] bg-black/[.02] dark:bg-white/[.02]'}`}
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <span className="text-sm font-semibold">{LABELS[s]}</span>
              <span className="text-xs muted tabular-nums">{columns[s].length}</span>
            </div>
            <div className="min-h-16 space-y-2">
              {columns[s].map((a) => (
                <div
                  key={a.id}
                  draggable
                  onDragStart={() => setDragId(a.id)}
                  className="card cursor-grab p-2.5 active:cursor-grabbing"
                >
                  <div className="flex items-start gap-2">
                    <ScoreBadge score={a.job?.match_score} />
                    <div className="min-w-0">
                      <Link to={`/jobs/${a.job_id}`} className="line-clamp-2 text-sm font-medium hover:underline">{a.job?.title}</Link>
                      <div className="truncate text-xs secondary">{a.job?.company}</div>
                    </div>
                  </div>
                  {a.applied_at && <div className="mt-1 text-xs muted">Applied {fmtDate(a.applied_at)}</div>}
                  {a.status === 'applied' && a.follow_up_at && !a.follow_up_done && (
                    <div className="mt-1"><Badge tone="amber">Follow up {fmtDate(a.follow_up_at)}</Badge></div>
                  )}
                  <div className="mt-2 flex items-center gap-1">
                    <select className="input flex-1 py-0.5 text-xs" value={a.status} onChange={(e) => move(a.id, e.target.value)} aria-label="Move to">
                      {statuses.map((x) => <option key={x} value={x}>{LABELS[x]}</option>)}
                    </select>
                    <button className="px-1 text-xs muted hover:text-red-600" title="Remove from tracker"
                      onClick={() => api.del(`/tracker/${a.id}`).then(board.reload)}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <Toast message={toast} onDone={() => setToast('')} />
    </div>
  )
}
