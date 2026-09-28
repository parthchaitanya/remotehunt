import { useState } from 'react'
import { api, fmtDate } from '../api.js'
import { ColumnChart, HBarChart } from '../components/Charts.jsx'
import { Button, Card, ErrorNote, Spinner, Stat, useLoad } from '../components/ui.jsx'

const pairs = (arr) => arr.map(([label, value]) => ({ label, value }))
const ELIG = { eligible: 'Eligible', unclear: 'Region unclear', ineligible: 'Not eligible' }
const APPLY = { direct_ats: 'Company ATS', company_site: 'Careers site', email: 'Email', linkedin: 'LinkedIn', naukri: 'Naukri', hn_comment: 'HN post', job_board: 'Job board' }

export default function Stats() {
  const [days, setDays] = useState(30)
  const { data, error, loading } = useLoad(() => api.get(`/stats?days=${days}`), [days])
  const reports = useLoad(() => api.get('/reports'))
  const [running, setRunning] = useState('')

  const runReport = async (kind) => {
    setRunning(kind)
    try { await api.post(`/reports/${kind}/run`); reports.reload() } finally { setRunning('') }
  }

  if (loading && !data) return <Spinner />
  if (error) return <ErrorNote error={error} />
  const d = data
  const funnel = Object.entries(d.funnel).map(([label, value]) => ({ label: label[0].toUpperCase() + label.slice(1), value }))
  const tick = Math.max(1, Math.ceil(d.per_day.length / 8))
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Stats</h1>
          <p className="text-sm muted">Hover or focus a bar for its value; “Table” shows the numbers.</p>
        </div>
        <select className="input" value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Time range">
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Jobs in window" value={d.jobs_in_window} sub={`${d.jobs_total} stored in total`} />
        <Stat label="Eligible" value={(d.eligibility.find(([k]) => k === 'eligible') || [0, 0])[1]} />
        <Stat label="Applied" value={d.funnel.applied + d.funnel.interview + d.funnel.offer} />
        <Stat label="Interviews" value={d.funnel.interview} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <ColumnChart title="New jobs per day" data={d.per_day.map((p) => ({ label: p.date.slice(5), value: p.count }))} tickEvery={tick} labelHeader="Date" />
        <ColumnChart title="Match-score distribution" subtitle="Jobs per 10-point score band" data={d.score_histogram.map((h) => ({ label: h.bucket, value: h.count }))} labelHeader="Score band" />
        <HBarChart title="Jobs by source" data={pairs(d.by_source)} labelHeader="Source" />
        <HBarChart title="Application funnel" data={funnel} labelHeader="Stage" valueHeader="Applications" />
        <HBarChart title="Most requested skills" data={pairs(d.top_skills)} labelHeader="Skill" />
        <HBarChart title="Skills you're missing (in jobs scoring ≥ 40)" data={pairs(d.top_missing_skills)} labelHeader="Skill" />
        <HBarChart title="Region eligibility" data={d.eligibility.map(([k, v]) => ({ label: ELIG[k] || k, value: v }))} labelHeader="Eligibility" />
        <HBarChart title="How you'd apply" data={d.apply_methods.map(([k, v]) => ({ label: APPLY[k] || k, value: v }))} labelHeader="Apply method" />
        <HBarChart title="Role family" data={pairs(d.by_role)} labelHeader="Role" />
      </div>

      <Card title="Reports" actions={<>
        <Button busy={running === 'weekly_checkin'} onClick={() => runReport('weekly_checkin')}>Run weekly check-in</Button>
        <Button busy={running === 'monthly_trends'} onClick={() => runReport('monthly_trends')}>Run market-trend report</Button>
      </>}>
        {reports.data?.length ? (
          <div className="space-y-3">
            {reports.data.slice(0, 4).map((r) => <ReportView key={r.id} r={r} />)}
          </div>
        ) : <p className="text-sm muted">Weekly check-ins run Mondays 09:00 IST; market-trend reports on the 1st of each month.</p>}
      </Card>
    </div>
  )
}

function ReportView({ r }) {
  const d = r.data
  if (r.kind === 'weekly_checkin') {
    return (
      <div className="rounded-lg border border-[var(--border)] p-3 text-sm">
        <div className="font-medium">Weekly check-in · {fmtDate(r.created_at)}</div>
        <p className="secondary">ATS {d.ats_score ?? '–'} ({d.ats_change_since_last_check >= 0 ? '+' : ''}{d.ats_change_since_last_check ?? 0}) · {d.jobs?.new_this_week} new jobs, {d.jobs?.high_match} high-match · applied {d.applications?.applied_this_week} this week</p>
        {d.nudge && <p className="text-amber-800 dark:text-amber-300">{d.nudge}</p>}
        {d.skill_priorities && <ul className="mt-1 text-xs secondary">{d.skill_priorities.map((s) => <li key={s.role}>{s.role} ({s.coverage}%): learn {s.learn_next.join(', ') || '—'}</li>)}</ul>}
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-[var(--border)] p-3 text-sm">
      <div className="font-medium">Market trends · {fmtDate(r.created_at)}</div>
      <p className="secondary">{d.jobs_seen} jobs in the last 30 days (previous period {d.jobs_prev_period}).</p>
      <p className="text-xs secondary">Top skills: {d.top_skills.slice(0, 8).map((s) => `${s.skill} ${s.share}%`).join(' · ')}</p>
      {d.rising_skills.length > 0 && <p className="text-xs secondary">Rising: {d.rising_skills.slice(0, 5).map((s) => `${s.skill} (+${s.change_pts} pts)`).join(' · ')}</p>}
      {d.top_companies?.length > 0 && <p className="text-xs secondary">Most active employers: {d.top_companies.slice(0, 6).map(([c, n]) => `${c} (${n})`).join(', ')}</p>}
      {Object.keys(d.salary_min_median || {}).length > 0 && <p className="text-xs secondary">Median minimum salary: {Object.entries(d.salary_min_median).map(([c, v]) => `${c} ${v.toLocaleString()}`).join(' · ')}</p>}
    </div>
  )
}
