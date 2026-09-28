import { useState } from 'react'
import { api } from '../api.js'
import { Badge, Button, Card, ErrorNote, Spinner, Toast, useLoad } from '../components/ui.jsx'

export default function Profiles() {
  const { data, error, loading, setData } = useLoad(() => api.get('/profiles'))
  const cons = useLoad(() => api.get('/profiles/consistency'))
  const [sel, setSel] = useState('linkedin')
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState('')

  if (loading && !data) return <Spinner />
  if (error) return <ErrorNote error={error} />
  const p = data.find((x) => x.platform === sel)
  const replace = (np) => setData(data.map((x) => (x.platform === np.platform ? np : x)))

  const generate = async () => {
    setBusy(true)
    try {
      replace(await api.post(`/profiles/${sel}/generate`))
      cons.reload()
    } catch (e) {
      setToast(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Profiles</h1>
        <p className="text-sm muted">Platform-ready text generated only from facts on your resume. Paste back what you publish to track completion and keyword consistency.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <div className="card h-fit p-2">
          {data.map((x) => (
            <button key={x.platform} onClick={() => setSel(x.platform)}
              className={`flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-sm ${sel === x.platform ? 'bg-[var(--series-1)] text-white' : 'hover:bg-black/5 dark:hover:bg-white/5'}`}>
              <span>{x.label}</span>
              <span className="text-xs tabular-nums opacity-80">{x.completion}%</span>
            </button>
          ))}
        </div>
        <div className="space-y-4">
          <Card title={p.label} actions={<Button variant="primary" busy={busy} onClick={generate}>{p.fields.some((f) => f.generated) ? 'Regenerate' : 'Generate text'}</Button>}>
            <div className="mb-3 h-2 rounded-full bg-[var(--grid)]" role="meter" aria-label="Completion" aria-valuenow={p.completion} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-2 rounded-full bg-[var(--series-1)]" style={{ width: `${p.completion}%` }} />
            </div>
            <div className="space-y-4">
              {p.fields.map((f) => <FieldEditor key={f.field} platform={sel} f={f} onSaved={(np) => { replace(np); cons.reload() }} setToast={setToast} />)}
            </div>
          </Card>
          <Card title="Completion checklist">
            <ul className="grid gap-1 sm:grid-cols-2">
              {p.checklist.map((i) => (
                <li key={i.key}>
                  <label className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={i.done} onChange={async (e) => replace(await api.post(`/profiles/${sel}/checklist`, { item: i.key, done: e.target.checked }))} />
                    <span className={i.done ? 'muted line-through' : ''}>{i.key}</span>
                  </label>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <Card title="Keyword consistency across platforms">
        {cons.loading && !cons.data ? <Spinner /> : cons.data && (
          <div className="space-y-3 text-sm">
            <p className="text-xs muted">Target keywords (from your resume + target roles): {cons.data.target_keywords.join(', ')}</p>
            {cons.data.issues.length > 0 ? (
              <ul className="space-y-1">{cons.data.issues.map((i) => <li key={i}>⚠ {i}</li>)}</ul>
            ) : <p className="text-green-700 dark:text-green-300">✓ Profiles are consistent.</p>}
            {cons.data.platforms.length > 0 && (
              <table className="w-full text-sm">
                <thead><tr className="text-left text-xs muted"><th className="py-1">Platform</th><th>Checked text</th><th className="text-right">Keyword coverage</th><th className="pl-3">Missing</th></tr></thead>
                <tbody>
                  {cons.data.platforms.map((r) => (
                    <tr key={r.platform} className="border-t border-[var(--grid)] align-top">
                      <td className="py-1.5">{r.platform}</td>
                      <td className="text-xs secondary">{r.source}</td>
                      <td className="text-right tabular-nums">{r.keyword_coverage}%</td>
                      <td className="pl-3 text-xs secondary">{r.missing_keywords.join(', ') || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </Card>
      <Toast message={toast} onDone={() => setToast('')} />
    </div>
  )
}

function FieldEditor({ platform, f, onSaved, setToast }) {
  const [current, setCurrent] = useState(f.current)
  const [saving, setSaving] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(f.generated)
      setToast('Copied')
    } catch {
      setToast('Copy failed – select the text manually')
    }
  }
  const save = async () => {
    setSaving(true)
    try { onSaved(await api.put(`/profiles/${platform}/current`, { field: f.field, text: current })) } finally { setSaving(false) }
  }
  return (
    <div>
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">{f.field.replace(/_/g, ' ')} <span className="text-xs font-normal muted">· {f.hint} · max {f.limit} chars</span></div>
        {f.generator && <Badge>{f.generator === 'llm' ? 'AI + guardrail' : 'Template'}</Badge>}
      </div>
      {f.generated ? (
        <div className="mt-1 rounded-lg bg-black/[.03] p-2 dark:bg-white/5">
          <pre className="prose-pre font-sans text-sm">{f.generated}</pre>
          <div className="mt-1 flex items-center justify-between text-xs muted">
            <span>{f.generated.length}/{f.limit}</span>
            <button className="underline" onClick={copy}>Copy</button>
          </div>
        </div>
      ) : <p className="mt-1 text-xs muted">Not generated yet.</p>}
      <details className="mt-1">
        <summary className="cursor-pointer text-xs muted">What's live on {platform} now? (for consistency tracking)</summary>
        <textarea className="input mt-1 w-full" rows={3} value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="Paste your current published text" />
        <Button className="mt-1" busy={saving} onClick={save}>Save current text</Button>
      </details>
    </div>
  )
}
