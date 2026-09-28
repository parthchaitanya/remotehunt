import { useEffect, useState } from 'react'

export function Card({ title, actions, children, className = '' }) {
  return (
    <section className={`card p-4 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold">{title}</h2>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

const BTN = {
  primary: 'bg-[var(--series-1)] text-white hover:bg-[var(--series-1-hover)]',
  secondary: 'border border-[var(--border)] hover:bg-black/5 dark:hover:bg-white/5',
  danger: 'border border-red-300 text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950',
  ghost: 'hover:bg-black/5 dark:hover:bg-white/10',
}

export function Button({ variant = 'secondary', className = '', busy, children, ...props }) {
  return (
    <button
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:opacity-50 ${BTN[variant]} ${className}`}
      disabled={busy || props.disabled}
      {...props}
    >
      {busy && <Spinner small />}
      {children}
    </button>
  )
}

export function Spinner({ small }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${small ? 'h-3 w-3' : 'h-5 w-5'}`}
      aria-label="Loading"
    />
  )
}

const TONES = {
  gray: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  blue: 'bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  green: 'bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300',
  amber: 'bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  red: 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
}

export function Badge({ tone = 'gray', children, title }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      {children}
    </span>
  )
}

export function ScoreBadge({ score }) {
  if (score === null || score === undefined) return <Badge>n/a</Badge>
  const tone = score >= 70 ? 'green' : score >= 45 ? 'amber' : 'gray'
  return (
    <span
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-bold ${TONES[tone]}`}
      title={`Match score ${score}/100`}
    >
      {score}
    </span>
  )
}

// Status badges always carry an icon + label (never colour alone).
export function EligibilityBadge({ eligible, reason }) {
  if (eligible === true) return <Badge tone="green" title={reason}>✓ Eligible</Badge>
  if (eligible === false) return <Badge tone="red" title={reason}>✕ Not eligible</Badge>
  return <Badge tone="amber" title={reason}>? Check region</Badge>
}

export function ScamBadge({ level, score }) {
  if (level === 'high') return <Badge tone="red" title={`Scam risk ${score}`}>⚠ High scam risk</Badge>
  if (level === 'medium') return <Badge tone="amber" title={`Scam risk ${score}`}>⚠ Some red flags</Badge>
  return null
}

const HEALTH = {
  ok: ['green', '● OK'],
  degraded: ['amber', '▲ Degraded'],
  down: ['red', '✕ Down'],
  unknown: ['gray', '○ Not run yet'],
  disabled: ['gray', '– Disabled'],
  unconfigured: ['gray', '○ Needs setup'],
  budget_exhausted: ['amber', '⏸ Budget used'],
}

export function HealthBadge({ status }) {
  const [tone, label] = HEALTH[status] || ['gray', status]
  return <Badge tone={tone}>{label}</Badge>
}

export function Stat({ label, value, sub }) {
  return (
    <div className="card p-4">
      <div className="text-xs font-medium muted uppercase tracking-wide">{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-xs secondary">{sub}</div>}
    </div>
  )
}

export function Empty({ children }) {
  return <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center text-sm muted">{children}</div>
}

export function ErrorNote({ error }) {
  if (!error) return null
  return <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{String(error.message || error)}</div>
}

export function useLoad(fn, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    setLoading(true)
    fn()
      .then((d) => alive && (setData(d), setError(null)))
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { data, error, loading, reload: () => setTick((t) => t + 1), setData }
}

export function Toast({ message, onDone }) {
  useEffect(() => {
    if (!message) return
    const t = setTimeout(onDone, 3500)
    return () => clearTimeout(t)
  }, [message, onDone])
  if (!message) return null
  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-sm rounded-lg bg-gray-900 px-4 py-2 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900">
      {message}
    </div>
  )
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-[var(--border)]">
      {tabs.map(([key, label]) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${value === key ? 'border-[var(--series-1)]' : 'border-transparent muted hover:text-[var(--text-primary)]'}`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
