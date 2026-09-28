import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, fmtDateTime } from '../api.js'
import { Badge, Button, Card, Empty, ErrorNote, Spinner, Toast, useLoad } from '../components/ui.jsx'

const CAT = { interview: ['blue', 'Interview'], rejection: ['red', 'Rejection'], application_update: ['gray', 'Application update'], recruiter: ['green', 'Recruiter'] }

export default function Settings() {
  const settings = useLoad(() => api.get('/settings'))
  const status = useLoad(() => api.get('/gmail/status'))
  const threads = useLoad(() => api.get('/gmail/threads'))
  const digests = useLoad(() => api.get('/digests'))
  const [params] = useSearchParams()
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState('')
  const [draft, setDraft] = useState(null)
  const [preview, setPreview] = useState(null)

  useEffect(() => {
    const g = params.get('gmail')
    if (g === 'connected') setToast('Gmail connected.')
    if (g === 'denied') setToast('Gmail connection was cancelled.')
    if (g === 'error') setToast(`Gmail connection failed (${params.get('reason') || 'unknown'}). Check that you signed in as the configured address.`)
  }, [params])

  const act = async (key, fn, msg) => {
    setBusy(key)
    try { const r = await fn(); if (msg) setToast(typeof msg === 'function' ? msg(r) : msg); return r } catch (e) { setToast(e.message) } finally { setBusy('') }
  }

  const connect = () => act('connect', async () => { const { url } = await api.get('/gmail/auth/start'); window.location.href = url })

  if (settings.loading && !settings.data) return <Spinner />
  if (settings.error) return <ErrorNote error={settings.error} />
  const s = settings.data
  const g = status.data
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Settings & Gmail</h1>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Gmail">
          {g && (
            <div className="space-y-2 text-sm">
              <p>
                Status: {g.connected ? <Badge tone="green">● Connected as {g.email}</Badge> : g.configured ? <Badge tone="amber">○ Not connected</Badge> : <Badge tone="red">✕ OAuth client not configured</Badge>}
              </p>
              <p className="text-xs muted">Scopes: gmail.modify (labels, drafts) + gmail.send (your daily digest to <b>{g.expected_email}</b> only). Tokens are Fernet-encrypted at rest. Recruiter replies are only ever saved as drafts.</p>
              <div className="flex flex-wrap gap-2">
                {!g.connected && <Button variant="primary" disabled={!g.configured} busy={busy === 'connect'} onClick={connect}>Connect Gmail</Button>}
                {g.connected && <Button busy={busy === 'sync'} onClick={() => act('sync', () => api.post('/gmail/sync'), (r) => `Scanned ${r.scanned}, labelled ${r.labeled} recruiter emails`).then(threads.reload)}>Sync & label now</Button>}
                {g.connected && <Button variant="danger" onClick={() => act('disc', () => api.post('/gmail/disconnect'), 'Disconnected and token revoked').then(status.reload)}>Disconnect</Button>}
              </div>
              {!g.configured && <p className="text-xs muted">Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in .env — see docs/SETUP.md.</p>}
            </div>
          )}
        </Card>
        <Card title="Configuration">
          <ul className="space-y-1 text-sm">
            <li>LLM (Groq, {s.llm.model}): {s.llm.configured ? <Badge tone="green">● Configured</Badge> : <Badge tone="amber">○ GROQ_API_KEY not set – rules/templates only</Badge>}</li>
            <li>Adzuna: {s.keys.adzuna ? <Badge tone="green">● Key set</Badge> : <Badge>○ Not set</Badge>}</li>
            <li>Jooble: {s.keys.jooble ? <Badge tone="green">● Key set</Badge> : <Badge>○ Not set</Badge>}</li>
            <li>Careerjet: {s.keys.careerjet ? <Badge tone="green">● Key set</Badge> : <Badge>○ Not set (disabled by default)</Badge>}</li>
            <li>Database: <span className="font-mono text-xs">{s.database}</span> · Time zone: {s.timezone}</li>
          </ul>
          <p className="mt-2 text-xs muted">Target roles: {s.profile.candidate.target_roles.join(', ')}. Edit config/profile.yaml to change preferences.</p>
          {s.scheduler.length > 0 && <ul className="mt-2 text-xs muted">{s.scheduler.map((j) => <li key={j.id}>{j.id}: next run {fmtDateTime(j.next_run)}</li>)}</ul>}
        </Card>
      </div>

      <Card title="Recruiter emails" actions={<span className="text-xs muted">Labelled under RemoteHunt/* in Gmail</span>}>
        {threads.loading && !threads.data ? <Spinner /> : threads.data?.length === 0 ? <Empty>No recruiter emails yet{g?.connected ? '' : ' — connect Gmail first'}.</Empty> : (
          <ul className="divide-y divide-[var(--grid)]">
            {threads.data?.map((t) => (
              <li key={t.id} className="flex flex-wrap items-start justify-between gap-2 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><Badge tone={CAT[t.category]?.[0]}>{CAT[t.category]?.[1] || t.category}</Badge><span className="font-medium">{t.subject}</span></div>
                  <div className="text-xs secondary">{t.from_name} · {fmtDateTime(t.received_at)} {t.awaiting_reply_since && '· awaiting their reply'}</div>
                  <div className="truncate text-xs muted">{t.snippet}</div>
                </div>
                <div className="flex gap-1">
                  <Button busy={busy === `d${t.id}`} onClick={() => act(`d${t.id}`, () => api.post(`/gmail/threads/${t.id}/draft-reply`, {}), 'Reply saved as a Gmail draft (not sent)').then((r) => r && setDraft(r))}>
                    {t.draft_id ? 'New reply draft' : 'Draft reply'}
                  </Button>
                  {t.awaiting_reply_since && <Button variant="ghost" onClick={() => act('dis', () => api.post(`/gmail/threads/${t.id}/dismiss`)).then(threads.reload)}>Dismiss reminder</Button>}
                </div>
              </li>
            ))}
          </ul>
        )}
        {draft && (
          <div className="mt-3 rounded-lg bg-black/[.03] p-3 dark:bg-white/5">
            <div className="mb-1 flex items-center justify-between text-xs muted">
              <span>Draft saved in Gmail — review and send it yourself.</span>
              <a className="underline" href={draft.open_url} target="_blank" rel="noreferrer">Open Gmail drafts ↗</a>
            </div>
            <pre className="prose-pre text-sm">{draft.body}</pre>
          </div>
        )}
      </Card>

      <Card title="Daily digest (08:00 IST)" actions={<>
        <Button onClick={async () => setPreview(await api.get('/digests/preview'))}>Preview next</Button>
        <Button variant="primary" busy={busy === 'dig'} onClick={() => act('dig', () => api.post('/digests/run', { send: true }), (r) => (r.sent ? 'Digest sent to your inbox' : `Digest saved (${r.send_error || 'not sent'})`)).then(digests.reload)}>Build & send now</Button>
      </>}>
        {preview && (
          <div className="mb-3 overflow-hidden rounded-lg border border-[var(--border)] bg-white">
            <iframe title="Digest preview" srcDoc={preview} sandbox="" className="h-96 w-full" />
          </div>
        )}
        {digests.data?.length === 0 ? <p className="text-sm muted">No digests yet.</p> : (
          <ul className="space-y-1 text-sm">
            {digests.data?.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2">
                <a className="hover:underline" href={`/api/digests/${d.id}`} target="_blank" rel="noreferrer">{d.subject}</a>
                <span className="text-xs muted">{d.sent ? '✓ sent' : d.send_error || 'stored'}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Toast message={toast} onDone={() => setToast('')} />
    </div>
  )
}
