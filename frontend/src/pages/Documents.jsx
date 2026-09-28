import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDateTime } from '../api.js'
import DocEditor from '../components/DocEditor.jsx'
import { Empty, ErrorNote, Spinner, Tabs, useLoad } from '../components/ui.jsx'

export default function Documents() {
  const [status, setStatus] = useState('draft')
  const { data, error, loading, reload } = useLoad(() => api.get(`/documents?status=${status}`), [status])
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">Tailored documents</h1>
        <p className="text-sm muted">Every document starts as a draft. Approve it to unlock PDF/DOCX export — nothing is sent anywhere.</p>
      </div>
      <Tabs tabs={[['draft', 'Drafts'], ['approved', 'Approved'], ['rejected', 'Rejected']]} value={status} onChange={setStatus} />
      <ErrorNote error={error} />
      {loading && !data ? <Spinner /> : data?.length === 0 ? (
        <Empty>No {status} documents. Open a high-match job and click “Tailor resume + cover letter”.</Empty>
      ) : (
        <div className="space-y-3">
          {data.map((d) => (
            <div key={d.id} className="space-y-1">
              <div className="text-xs muted">
                For <Link className="text-[var(--series-1)] hover:underline" to={`/jobs/${d.job?.id}`}>{d.job?.title} – {d.job?.company}</Link> · {fmtDateTime(d.created_at)}
              </div>
              <DocEditor doc={d} onChange={reload} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
