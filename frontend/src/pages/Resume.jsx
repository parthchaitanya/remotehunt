import { useRef, useState } from 'react'
import { api, fmtDateTime } from '../api.js'
import { Badge, Button, Card, Empty, ErrorNote, Spinner, Tabs, Toast, useLoad } from '../components/ui.jsx'

export default function Resume() {
  const active = useLoad(() => api.get('/resume/active'))
  const versions = useLoad(() => api.get('/resume/versions'))
  const [tab, setTab] = useState('ats')
  const [toast, setToast] = useState('')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)

  const upload = async (e) => {
    e.preventDefault()
    const f = fileRef.current?.files?.[0]
    if (!f) return
    const form = new FormData()
    form.append('file', f)
    form.append('label', e.target.label.value)
    setUploading(true)
    try {
      const v = await api.upload('/resume/upload', form)
      setToast(`Uploaded v${v.version_no} – ATS ${v.ats_score}. Jobs are being rescored in the background.`)
      active.reload()
      versions.reload()
      e.target.reset()
    } catch (err) {
      setToast(err.message)
    } finally {
      setUploading(false)
    }
  }

  const v = active.data
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Resume</h1>
          <p className="text-sm muted">PDF or DOCX. Each upload is a new version; rollback never deletes history.</p>
        </div>
        <form onSubmit={upload} className="card flex flex-wrap items-center gap-2 p-2">
          <input ref={fileRef} type="file" accept=".pdf,.docx" className="text-sm" required />
          <input name="label" className="input w-36" placeholder="Label (optional)" />
          <Button variant="primary" busy={uploading}>Upload</Button>
        </form>
      </div>
      <ErrorNote error={active.error} />
      {active.loading && !v ? <Spinner /> : !v ? <Empty>No resume yet — upload one to get started.</Empty> : (
        <>
          <div className="grid gap-3 md:grid-cols-[220px_1fr]">
            <div className="card flex flex-col items-center justify-center p-5 text-center">
              <div className="text-xs font-medium uppercase tracking-wide muted">ATS score</div>
              <div className="text-5xl font-semibold tabular-nums">{v.ats.score}</div>
              <Badge tone={v.ats.score >= 70 ? 'green' : v.ats.score >= 55 ? 'amber' : 'red'}>{v.ats.grade}</Badge>
              <div className="mt-2 text-xs muted">{v.label} · {v.filename}</div>
            </div>
            <Card title="Top fixes">
              <ol className="list-decimal space-y-1 pl-5 text-sm">
                {v.ats.top_tips.map((t) => <li key={t}>{t}</li>)}
              </ol>
            </Card>
          </div>
          <Tabs tabs={[['ats', 'ATS breakdown'], ['suggestions', 'Line-by-line suggestions'], ['gap', 'Skill gap'], ['versions', 'Versions & diff'], ['parsed', 'Parsed JSON']]} value={tab} onChange={setTab} />
          {tab === 'ats' && <AtsBreakdown ats={v.ats} />}
          {tab === 'suggestions' && <Suggestions />}
          {tab === 'gap' && <SkillGap />}
          {tab === 'versions' && <Versions versions={versions} onChange={() => { active.reload(); versions.reload() }} setToast={setToast} />}
          {tab === 'parsed' && <Card><pre className="prose-pre max-h-[600px] overflow-auto text-xs">{JSON.stringify(v.parsed, null, 2)}</pre></Card>}
        </>
      )}
      <Toast message={toast} onDone={() => setToast('')} />
    </div>
  )
}

function AtsBreakdown({ ats }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {ats.breakdown.map((c) => {
        const pct = (c.score / c.max) * 100
        return (
          <div key={c.category} className="card p-4">
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-semibold">{c.category}</span>
              <span className="text-sm tabular-nums"><b>{c.score}</b><span className="muted"> / {c.max}</span></span>
            </div>
            <div className="mt-2 h-2 rounded-full bg-[var(--grid)]" role="meter" aria-valuenow={c.score} aria-valuemin={0} aria-valuemax={c.max} aria-label={c.category}>
              <div className="h-2 rounded-full bg-[var(--series-1)]" style={{ width: `${pct}%` }} />
            </div>
            <ul className="mt-2 space-y-0.5 text-xs secondary">{c.details.map((d) => <li key={d}>✓ {d}</li>)}</ul>
            {c.tips.length > 0 && <ul className="mt-1 space-y-0.5 text-xs text-amber-800 dark:text-amber-300">{c.tips.map((t) => <li key={t}>→ {t}</li>)}</ul>}
          </div>
        )
      })}
    </div>
  )
}

function Suggestions() {
  const [refresh, setRefresh] = useState(0)
  const { data, error, loading } = useLoad(() => api.post(`/resume/suggestions${refresh ? '?refresh=true' : ''}`), [refresh])
  if (loading) return <div className="flex items-center gap-2 text-sm muted"><Spinner small /> Analysing each line…</div>
  if (error) return <ErrorNote error={error} />
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs muted">
          {data.llm_available ? 'AI rewrites by Groq are checked by the guardrail: anything adding a skill, number or credential you don’t have is discarded.' : 'Groq key not set – showing rule-based feedback only. Add GROQ_API_KEY for AI rewrites.'}
        </p>
        <Button onClick={() => setRefresh((r) => r + 1)}>Regenerate</Button>
      </div>
      {data.suggestions.map((s) => (
        <div key={s.id} className="card p-3">
          <div className="text-xs muted">{s.section} · {s.context}</div>
          <p className="mt-1 text-sm">{s.original}</p>
          {s.issues.length > 0 && <ul className="mt-1 flex flex-wrap gap-1">{s.issues.map((i) => <Badge key={i} tone="amber">{i}</Badge>)}</ul>}
          {s.suggestion && (
            <div className="mt-2 rounded-lg bg-green-50 p-2 text-sm dark:bg-green-950/40">
              <span className="text-xs font-medium text-green-800 dark:text-green-300">{s.source === 'llm' ? 'Suggested rewrite' : 'Try'}: </span>{s.suggestion}
              {s.reason && <div className="text-xs muted">{s.reason}</div>}
            </div>
          )}
          {!s.suggestion && s.reason && <p className="mt-1 text-xs muted">{s.reason}</p>}
          {s.issues.length === 0 && !s.suggestion && <p className="mt-1 text-xs text-green-700 dark:text-green-300">✓ Looks good</p>}
        </div>
      ))}
    </div>
  )
}

function SkillGap() {
  const { data, error, loading } = useLoad(() => api.get('/resume/skill-gap'))
  if (loading) return <Spinner />
  if (error) return <ErrorNote error={error} />
  return (
    <div className="grid gap-3 lg:grid-cols-3">
      {data.map((r) => (
        <Card key={r.role} title={r.role} actions={<Badge tone={r.coverage >= 60 ? 'green' : 'amber'}>{r.coverage}% coverage</Badge>}>
          <div className="space-y-2 text-sm">
            <div><span className="text-xs muted">You have: </span>{r.have.map((s) => <Badge key={s} tone="green">{s}</Badge>)}</div>
            {r.missing_core.length > 0 && <div><span className="text-xs muted">Missing core: </span>{r.missing_core.map((s) => <Badge key={s} tone="amber">{s}</Badge>)}</div>}
            {r.in_demand_missing.length > 0 && (
              <div>
                <div className="text-xs muted">In demand in {r.market_jobs_analyzed} recent {r.role} jobs:</div>
                <ul className="mt-1 text-xs">
                  {r.in_demand_missing.slice(0, 6).map((d) => <li key={d.skill}>{d.skill} <span className="muted">— {d.pct}% of jobs</span></li>)}
                </ul>
              </div>
            )}
            <div>
              <div className="text-xs font-medium">Learn next</div>
              <ol className="list-decimal pl-5 text-xs secondary">
                {r.priorities.map((p) => <li key={p.key}><b>{p.skill}</b>{p.hint && ` – ${p.hint}`}</li>)}
              </ol>
            </div>
          </div>
        </Card>
      ))}
    </div>
  )
}

function Versions({ versions, onChange, setToast }) {
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [diff, setDiff] = useState(null)
  const [error, setError] = useState(null)
  if (versions.loading && !versions.data) return <Spinner />
  const list = versions.data || []
  const doDiff = async () => {
    setError(null)
    try { setDiff(await api.get(`/resume/diff?a=${a}&b=${b}`)) } catch (e) { setError(e) }
  }
  const rollback = async (id) => {
    const r = await api.post(`/resume/versions/${id}/rollback`)
    setToast(`Rolled back – now active as v${r.version_no}`)
    onChange()
  }
  return (
    <div className="space-y-3">
      <Card>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs muted"><th className="py-1">Version</th><th>Uploaded</th><th>File</th><th className="text-right">ATS</th><th /></tr></thead>
          <tbody>
            {list.map((v) => (
              <tr key={v.id} className="border-t border-[var(--grid)]">
                <td className="py-1.5">{v.label} {v.is_active && <Badge tone="green">active</Badge>}</td>
                <td className="secondary">{fmtDateTime(v.created_at)}</td>
                <td className="secondary">{v.filename}</td>
                <td className="text-right tabular-nums">{v.ats_score}</td>
                <td className="text-right">{!v.is_active && <Button variant="ghost" onClick={() => rollback(v.id)}>Roll back to this</Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {list.length >= 2 && (
        <Card title="Compare versions">
          <div className="flex flex-wrap items-center gap-2">
            <select className="input" value={a} onChange={(e) => setA(e.target.value)} aria-label="From version"><option value="">From…</option>{list.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}</select>
            <span className="muted">→</span>
            <select className="input" value={b} onChange={(e) => setB(e.target.value)} aria-label="To version"><option value="">To…</option>{list.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}</select>
            <Button variant="primary" disabled={!a || !b} onClick={doDiff}>Show diff</Button>
          </div>
          <ErrorNote error={error} />
          {diff && (
            <div className="mt-3 space-y-3 text-sm">
              <p>ATS {diff.from.ats_score} → {diff.to.ats_score} (<b>{diff.ats_delta >= 0 ? '+' : ''}{diff.ats_delta}</b>)</p>
              {diff.skills_added.length > 0 && <p>Skills added: {diff.skills_added.map((s) => <Badge key={s} tone="green">+ {s}</Badge>)}</p>}
              {diff.skills_removed.length > 0 && <p>Skills removed: {diff.skills_removed.map((s) => <Badge key={s} tone="red">− {s}</Badge>)}</p>}
              {diff.sections.length === 0 && <p className="muted">No content differences.</p>}
              {diff.sections.map((s) => (
                <div key={s.section}>
                  <div className="text-xs font-semibold uppercase muted">{s.section}</div>
                  {s.changes.map((c, i) => (
                    <div key={i} className="mt-1 font-mono text-xs">
                      {c.removed.map((l) => <div key={'r' + l} className="bg-red-50 px-2 text-red-800 dark:bg-red-950/50 dark:text-red-300">− {l}</div>)}
                      {c.added.map((l) => <div key={'a' + l} className="bg-green-50 px-2 text-green-800 dark:bg-green-950/50 dark:text-green-300">+ {l}</div>)}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
