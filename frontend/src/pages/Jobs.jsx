import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, fmtDate, qs, timeAgo } from '../api.js'
import {
  Badge, Button, Card, Empty, EligibilityBadge, ErrorNote, ScamBadge, ScoreBadge, Spinner, Toast, useLoad,
} from '../components/ui.jsx'
import DocEditor from '../components/DocEditor.jsx'

const DEFAULT_FILTERS = { q: '', min_score: 0, source: '', eligible: 'maybe', remote: '', role: '', apply_method: '', sort: 'score', show_hidden: false }

export default function Jobs() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [page, setPage] = useState(0)
  const opts = useLoad(() => api.get('/jobs/filters'))
  const list = useLoad(() => api.get(`/jobs${qs({ ...filters, limit: 50, offset: page * 50 })}`), [JSON.stringify(filters), page])
  const set = (k, v) => { setPage(0); setFilters((f) => ({ ...f, [k]: v })) }
  const [rescoring, setRescoring] = useState(false)
  const rescore = async () => {
    setRescoring(true)
    try { await api.post('/jobs/rescore') } finally { setRescoring(false); list.reload() }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className={`${id ? 'hidden xl:block' : ''} space-y-3`}>
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">Jobs</h1>
          <Button variant="ghost" busy={rescoring} onClick={rescore} title="Re-run eligibility, scam and match scoring on all stored jobs">Rescore all</Button>
        </div>
        <div className="card flex flex-wrap items-center gap-2 p-3">
          <input className="input min-w-40 flex-1" placeholder="Search title, company, text…" value={filters.q} onChange={(e) => set('q', e.target.value)} />
          <select className="input" value={filters.eligible} onChange={(e) => set('eligible', e.target.value)} aria-label="Eligibility">
            <option value="maybe">Eligible + unclear</option>
            <option value="yes">Eligible only</option>
            <option value="any">Any region</option>
            <option value="no">Not eligible</option>
          </select>
          <select className="input" value={filters.remote} onChange={(e) => set('remote', e.target.value)} aria-label="Work type">
            <option value="">Remote + hybrid + any</option>
            <option value="remote">Remote only</option>
            <option value="hybrid">Hybrid only</option>
            <option value="onsite">On-site only</option>
          </select>
          <select className="input" value={filters.min_score} onChange={(e) => set('min_score', e.target.value)} aria-label="Minimum score">
            {[0, 30, 45, 60, 70, 80].map((s) => <option key={s} value={s}>{s ? `Score ≥ ${s}` : 'Any score'}</option>)}
          </select>
          <select className="input" value={filters.role} onChange={(e) => set('role', e.target.value)} aria-label="Role">
            <option value="">All roles</option>
            {opts.data?.roles.map((r) => <option key={r}>{r}</option>)}
          </select>
          <select className="input" value={filters.source} onChange={(e) => set('source', e.target.value)} aria-label="Source">
            <option value="">All sources</option>
            {opts.data?.sources.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select className="input" value={filters.sort} onChange={(e) => set('sort', e.target.value)} aria-label="Sort">
            <option value="score">Best match</option>
            <option value="newest">Newest seen</option>
            <option value="posted">Recently posted</option>
          </select>
          <label className="flex items-center gap-1 text-xs secondary">
            <input type="checkbox" checked={filters.show_hidden} onChange={(e) => set('show_hidden', e.target.checked)} /> show hidden
          </label>
        </div>
        <ErrorNote error={list.error} />
        {list.loading && !list.data ? <Spinner /> : (
          <>
            <p className="text-xs muted">{list.data?.total ?? 0} jobs</p>
            {list.data?.items.length === 0 && <Empty>No jobs match these filters.</Empty>}
            <ul className="space-y-2">
              {list.data?.items.map((j) => (
                <li key={j.id}>
                  <button
                    onClick={() => navigate(`/jobs/${j.id}`)}
                    className={`card flex w-full items-start gap-3 p-3 text-left hover:border-[var(--series-1)] ${String(j.id) === id ? 'border-[var(--series-1)]' : ''}`}
                  >
                    <ScoreBadge score={j.match_score} />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">{j.title}</div>
                      <div className="text-xs secondary">{j.company || 'Unknown company'} · {j.location || j.remote_type} · {timeAgo(j.first_seen_at)}</div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        <EligibilityBadge eligible={j.eligible} reason={j.eligibility_reason} />
                        <ScamBadge level={j.scam_level} score={j.scam_score} />
                        {j.remote_type !== 'unknown' && <Badge tone={j.remote_type === 'hybrid' ? 'amber' : 'gray'}>{{ remote: '⌂ Remote', hybrid: '⇄ Hybrid', onsite: '▣ On-site' }[j.remote_type]}</Badge>}
                        <Badge>{j.apply_method_label}</Badge>
                        {j.role_family && <Badge tone="blue">{j.role_family}</Badge>}
                        {j.tracker_status && <Badge tone="green">{j.tracker_status}</Badge>}
                      </div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
            <div className="flex justify-between">
              <Button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>← Prev</Button>
              <Button disabled={(page + 1) * 50 >= (list.data?.total || 0)} onClick={() => setPage((p) => p + 1)}>Next →</Button>
            </div>
          </>
        )}
      </div>
      <div>
        {id ? <JobDetail id={id} onChange={list.reload} /> : (
          <div className="hidden xl:block"><Empty>Select a job to see why it matches, what's missing, and to tailor documents.</Empty></div>
        )}
      </div>
    </div>
  )
}

function JobDetail({ id, onChange }) {
  const { data: j, error, loading, reload } = useLoad(() => api.get(`/jobs/${id}`), [id])
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState('')
  const [expanded, setExpanded] = useState(false)
  useEffect(() => setExpanded(false), [id])

  const act = async (key, fn, msg) => {
    setBusy(key)
    try {
      await fn()
      if (msg) setToast(msg)
      reload()
      onChange?.()
    } catch (e) {
      setToast(e.message)
    } finally {
      setBusy('')
    }
  }

  if (loading && !j) return <Spinner />
  if (error) return <ErrorNote error={error} />
  const high = (j.match_score ?? 0) >= j.tailor_min_score
  const b = j.match_breakdown || {}
  return (
    <div className="space-y-3 xl:sticky xl:top-4">
      <Link to="/jobs" className="text-xs text-[var(--series-1)] xl:hidden">← Back to list</Link>
      <Card>
        <div className="flex items-start gap-3">
          <ScoreBadge score={j.match_score} />
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold leading-snug">{j.title}</h2>
            <div className="text-sm secondary">{j.company} · {j.location || j.remote_type} {j.salary_text && `· ${j.salary_text}`}</div>
            <div className="mt-1 text-xs muted">via {j.source} · posted {fmtDate(j.posted_at)} · first seen {timeAgo(j.first_seen_at)}</div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <a href={j.apply_url || j.url} target="_blank" rel="noreferrer" className="inline-flex items-center rounded-lg bg-[var(--series-1)] px-3 py-1.5 text-sm font-medium text-white">
            Open posting ↗
          </a>
          {j.tracker_status ? <Badge tone="green">In tracker: {j.tracker_status}</Badge> : (
            <Button busy={busy === 'track'} onClick={() => act('track', () => api.post('/tracker', { job_id: j.id, status: 'saved' }), 'Saved to tracker')}>+ Save to tracker</Button>
          )}
          <Button busy={busy === 'tailor'} variant={high ? 'primary' : 'secondary'}
            onClick={() => act('tailor', () => api.post(`/jobs/${j.id}/tailor${high ? '' : '?force=true'}`), 'Draft resume + cover letter created – review and approve below')}>
            {high ? 'Tailor resume + cover letter' : 'Tailor anyway'}
          </Button>
          <Button variant="ghost" onClick={() => act('hide', () => api.post(`/jobs/${j.id}/hide`, { hidden: !j.hidden }))}>{j.hidden ? 'Unhide' : 'Hide'}</Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-1">
          <EligibilityBadge eligible={j.eligible} reason={j.eligibility_reason} />
          <ScamBadge level={j.scam_level} score={j.scam_score} />
          <Badge>{j.apply_method_label}</Badge>
          {j.employment_type && <Badge>{j.employment_type}</Badge>}
        </div>
        <p className="mt-2 text-xs secondary">{j.eligibility_reason}</p>
      </Card>

      <Card title="Why it matches">
        <ul className="list-disc space-y-1 pl-5 text-sm">
          {j.match_reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-lg bg-black/[.03] p-2 dark:bg-white/5"><div className="font-semibold tabular-nums">{Math.round((b.semantic || 0) * 100)}%</div><div className="muted">semantic (45%)</div></div>
          <div className="rounded-lg bg-black/[.03] p-2 dark:bg-white/5"><div className="font-semibold tabular-nums">{Math.round((b.keyword || 0) * 100)}%</div><div className="muted">skills (35%)</div></div>
          <div className="rounded-lg bg-black/[.03] p-2 dark:bg-white/5"><div className="font-semibold tabular-nums">{Math.round((b.title || 0) * 100)}%</div><div className="muted">title (20%)</div></div>
        </div>
        {b.penalty > 0 && <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">−{b.penalty} points for seniority / years required</p>}
        <div className="mt-3 space-y-2 text-sm">
          {j.matched_skills.length > 0 && <div><span className="text-xs muted">You have: </span>{j.matched_skills.map((s) => <Badge key={s} tone="green">{s}</Badge>)}</div>}
          {j.missing_skills.length > 0 && <div><span className="text-xs muted">Missing: </span>{j.missing_skills.map((s) => <Badge key={s} tone="amber">{s}</Badge>)}</div>}
        </div>
      </Card>

      {j.scam_flags.length > 0 && (
        <Card title="Red flags">
          <ul className="space-y-1 text-sm">
            {j.scam_flags.map((f) => <li key={f.code}>⚠ {f.message} {f.evidence && <span className="text-xs muted">“{f.evidence}”</span>}</li>)}
          </ul>
        </Card>
      )}

      {j.documents.length > 0 && (
        <Card title="Tailored documents (drafts need your approval)">
          <div className="space-y-3">
            {j.documents.map((d) => <DocEditor key={d.id} doc={d} onChange={reload} />)}
          </div>
        </Card>
      )}

      <Card title="Description" actions={<button className="text-xs muted hover:underline" onClick={() => setExpanded((e) => !e)}>{expanded ? 'Collapse' : 'Expand'}</button>}>
        <div className={`prose-pre text-sm secondary ${expanded ? '' : 'max-h-64 overflow-hidden'}`}>{j.description || 'No description (from an alert email). Open the posting for details.'}</div>
        {j.also_seen_on.length > 0 && (
          <p className="mt-2 text-xs muted">Also listed on: {j.also_seen_on.map((s) => <a key={s.url} className="mr-2 underline" href={s.url} target="_blank" rel="noreferrer">{s.source}</a>)}</p>
        )}
      </Card>
      <Toast message={toast} onDone={() => setToast('')} />
    </div>
  )
}
