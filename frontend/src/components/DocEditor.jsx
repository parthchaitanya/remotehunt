import { useState } from 'react'
import { api } from '../api.js'
import { Badge, Button, ErrorNote } from './ui.jsx'

// Review / edit / approve a tailored resume or cover letter. Export is only possible once approved.
export default function DocEditor({ doc, onChange }) {
  const [editing, setEditing] = useState(false)
  const [content, setContent] = useState(doc.content)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState(null)
  const g = doc.guardrail || {}

  const run = async (key, fn) => {
    setBusy(key)
    setError(null)
    try {
      await fn()
      onChange?.()
    } catch (e) {
      setError(e)
    } finally {
      setBusy('')
    }
  }

  const save = () => run('save', async () => {
    await api.put(`/documents/${doc.id}`, { content })
    setEditing(false)
  })

  const isResume = doc.kind === 'resume'
  const statusTone = doc.status === 'approved' ? 'green' : doc.status === 'rejected' ? 'red' : 'amber'
  return (
    <div className="rounded-lg border border-[var(--border)] p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{isResume ? 'Tailored resume' : 'Cover letter'}</span>
          <Badge tone={statusTone}>{doc.status === 'approved' ? '✓ Approved' : doc.status === 'rejected' ? '✕ Rejected' : '● Draft'}</Badge>
          <Badge>{doc.generator === 'llm' ? 'AI (Groq) + guardrail' : 'Template'}</Badge>
          {g.passed ? <Badge tone="green">✓ Guardrail passed</Badge> : <Badge tone="red">✕ {g.violations?.length} guardrail issue(s)</Badge>}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {!editing && <Button onClick={() => { setContent(doc.content); setEditing(true) }}>Edit</Button>}
          {doc.status !== 'approved' && !editing && (
            <Button variant="primary" busy={busy === 'approve'} onClick={() => run('approve', () => api.post(`/documents/${doc.id}/approve`))}>Approve</Button>
          )}
          {doc.status === 'approved' && (
            <>
              <a className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm" href={`/api/documents/${doc.id}/export?format=pdf`}>PDF ↓</a>
              <a className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm" href={`/api/documents/${doc.id}/export?format=docx`}>DOCX ↓</a>
            </>
          )}
          {doc.status !== 'rejected' && !editing && (
            <Button variant="ghost" busy={busy === 'reject'} onClick={() => run('reject', () => api.post(`/documents/${doc.id}/reject`))}>Reject</Button>
          )}
        </div>
      </div>
      <ErrorNote error={error} />
      {g.violations?.length > 0 && (
        <ul className="mt-2 list-disc pl-5 text-xs text-red-700 dark:text-red-300">
          {g.violations.map((v) => <li key={v.type + v.value}>{v.message}</li>)}
        </ul>
      )}
      {g.rejected_ai_output?.length > 0 && (
        <p className="mt-2 text-xs muted">
          The guardrail discarded AI text that claimed: {g.rejected_ai_output.map((v) => v.value).join(', ')} — only facts from your resume are kept.
        </p>
      )}

      {editing ? (
        isResume ? <ResumeFields content={content} setContent={setContent} /> : <LetterFields content={content} setContent={setContent} />
      ) : isResume ? <ResumePreview c={doc.content} /> : <LetterPreview c={doc.content} />}
      {editing && (
        <div className="mt-2 flex gap-2">
          <Button variant="primary" busy={busy === 'save'} onClick={save}>Save (re-checks guardrail)</Button>
          <Button onClick={() => setEditing(false)}>Cancel</Button>
        </div>
      )}
    </div>
  )
}

function ResumePreview({ c }) {
  return (
    <div className="mt-3 space-y-2 text-sm">
      <p><span className="text-xs font-semibold uppercase muted">Summary</span><br />{c.summary}</p>
      {c.experience?.map((e, i) => (
        <div key={i}>
          <div className="font-medium">{e.title} – {e.organization}</div>
          <ul className="list-disc pl-5 secondary">{e.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
        </div>
      ))}
      {c.projects?.map((p, i) => (
        <div key={i}>
          <div className="font-medium">{p.name}</div>
          <ul className="list-disc pl-5 secondary">{p.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
        </div>
      ))}
      <p className="text-xs muted">Skills order: {c.skills?.map((s) => s.items.slice(0, 3).join(', ')).join(' · ')}</p>
      {c.changes?.length > 0 && <p className="text-xs muted">Changes: {c.changes.join('; ')}</p>}
      {c.keywords_missing?.length > 0 && <p className="text-xs muted">Job keywords you don't have (not added): {c.keywords_missing.join(', ')}</p>}
    </div>
  )
}

function LetterPreview({ c }) {
  return (
    <div className="mt-3 space-y-2 text-sm">
      <p>{c.greeting}</p>
      {c.paragraphs?.map((p, i) => <p key={i} className="secondary">{p}</p>)}
      <p className="prose-pre">{c.closing}</p>
    </div>
  )
}

function ResumeFields({ content, setContent }) {
  const upd = (path, value) => {
    const next = structuredClone(content)
    let o = next
    for (let i = 0; i < path.length - 1; i++) o = o[path[i]]
    o[path[path.length - 1]] = value
    setContent(next)
  }
  return (
    <div className="mt-3 space-y-3 text-sm">
      <label className="block">
        <span className="text-xs muted">Summary</span>
        <textarea className="input mt-1 w-full" rows={4} value={content.summary} onChange={(e) => upd(['summary'], e.target.value)} />
      </label>
      {['experience', 'projects'].map((sec) => content[sec]?.map((e, i) => (
        <div key={sec + i}>
          <div className="text-xs font-medium">{e.title || e.name}</div>
          {e.bullets.map((b, bi) => (
            <textarea key={bi} className="input mt-1 w-full" rows={2} value={b} onChange={(ev) => upd([sec, i, 'bullets', bi], ev.target.value)} />
          ))}
        </div>
      )))}
    </div>
  )
}

function LetterFields({ content, setContent }) {
  return (
    <div className="mt-3 space-y-2">
      <input className="input w-full" value={content.greeting} onChange={(e) => setContent({ ...content, greeting: e.target.value })} />
      {content.paragraphs.map((p, i) => (
        <textarea key={i} className="input w-full" rows={4} value={p}
          onChange={(e) => setContent({ ...content, paragraphs: content.paragraphs.map((x, j) => (j === i ? e.target.value : x)) })} />
      ))}
      <textarea className="input w-full" rows={2} value={content.closing} onChange={(e) => setContent({ ...content, closing: e.target.value })} />
    </div>
  )
}
