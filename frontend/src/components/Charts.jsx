import { useRef, useState } from 'react'

// Single-series bar charts: one hue (--series-1), 4px rounded data-ends anchored at the baseline,
// 2px gaps between bars, recessive grid, hover + keyboard-focus tooltips, and a table view.

function Tooltip({ tip }) {
  if (!tip) return null
  return (
    <div
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2 py-1 text-xs shadow-md"
      style={{ left: tip.x, top: tip.y - 6 }}
    >
      <div className="font-semibold tabular-nums text-[var(--text-primary)]">{tip.value}</div>
      <div className="secondary">{tip.label}</div>
    </div>
  )
}

function DataTable({ data, labelHeader, valueHeader }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="muted text-left text-xs">
          <th className="py-1 font-medium">{labelHeader}</th>
          <th className="py-1 text-right font-medium">{valueHeader}</th>
        </tr>
      </thead>
      <tbody>
        {data.map((d) => (
          <tr key={d.label} className="border-t border-[var(--grid)]">
            <td className="py-1">{d.label}</td>
            <td className="py-1 text-right tabular-nums">{d.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ChartFrame({ title, subtitle, children, table }) {
  const [showTable, setShowTable] = useState(false)
  return (
    <section className="card p-4">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle && <p className="text-xs muted">{subtitle}</p>}
        </div>
        {table && (
          <button className="text-xs muted underline-offset-2 hover:underline" onClick={() => setShowTable((s) => !s)}>
            {showTable ? 'Chart' : 'Table'}
          </button>
        )}
      </div>
      {showTable ? table : children}
    </section>
  )
}

/** Horizontal bars for categories. data: [{label, value}] */
export function HBarChart({ title, subtitle, data, valueHeader = 'Jobs', labelHeader = 'Category', max }) {
  const [tip, setTip] = useState(null)
  const wrap = useRef(null)
  const top = max ?? Math.max(1, ...data.map((d) => d.value))
  const show = (e, d) => {
    const r = wrap.current.getBoundingClientRect()
    const b = e.currentTarget.getBoundingClientRect()
    setTip({ x: b.left - r.left + b.width / 2, y: b.top - r.top, label: d.label, value: d.value })
  }
  return (
    <ChartFrame title={title} subtitle={subtitle} table={<DataTable data={data} labelHeader={labelHeader} valueHeader={valueHeader} />}>
      {data.length === 0 || data.every((d) => !d.value) ? (
        <p className="text-sm muted">No data yet.</p>
      ) : (
        <div ref={wrap} className="relative space-y-[2px]" onMouseLeave={() => setTip(null)}>
          {data.map((d) => (
            <div key={d.label} className="grid grid-cols-[minmax(90px,34%)_1fr_auto] items-center gap-2 text-xs">
              <span className="truncate secondary" title={d.label}>{d.label}</span>
              <div className="h-5">
                <div
                  tabIndex={0}
                  role="img"
                  aria-label={`${d.label}: ${d.value}`}
                  onMouseEnter={(e) => show(e, d)}
                  onFocus={(e) => show(e, d)}
                  onBlur={() => setTip(null)}
                  className="h-full rounded-r-[4px] bg-[var(--series-1)] outline-none transition-colors hover:bg-[var(--series-1-hover)] focus:bg-[var(--series-1-hover)]"
                  style={{ width: d.value ? `${Math.max(1, (d.value / top) * 100)}%` : 0 }}
                />
              </div>
              <span className="w-10 text-right tabular-nums secondary">{d.value}</span>
            </div>
          ))}
          <Tooltip tip={tip} />
        </div>
      )}
    </ChartFrame>
  )
}

/** Vertical columns (time series / histogram). data: [{label, value}] */
export function ColumnChart({ title, subtitle, data, height = 160, valueHeader = 'Jobs', labelHeader = 'Date', tickEvery = 1 }) {
  const [tip, setTip] = useState(null)
  const wrap = useRef(null)
  const top = Math.max(1, ...data.map((d) => d.value))
  const niceTop = top <= 5 ? top : Math.ceil(top / 5) * 5
  const show = (e, d) => {
    const r = wrap.current.getBoundingClientRect()
    const b = e.currentTarget.getBoundingClientRect()
    setTip({ x: b.left - r.left + b.width / 2, y: b.top - r.top, label: d.label, value: d.value })
  }
  const grid = [0, 0.5, 1]
  return (
    <ChartFrame title={title} subtitle={subtitle} table={<DataTable data={data} labelHeader={labelHeader} valueHeader={valueHeader} />}>
      <div ref={wrap} className="relative pl-8" onMouseLeave={() => setTip(null)}>
        <div className="relative" style={{ height }}>
          {grid.map((g) => (
            <div key={g} className="absolute left-0 right-0 border-t border-[var(--grid)]" style={{ bottom: `${g * 100}%` }}>
              <span className="absolute -left-8 -translate-y-1/2 text-[10px] tabular-nums muted">{Math.round(niceTop * g)}</span>
            </div>
          ))}
          <div className="absolute inset-0 flex items-end gap-[2px]">
            {data.map((d) => (
              <div key={d.label} className="flex h-full flex-1 items-end">
                <div
                  tabIndex={0}
                  role="img"
                  aria-label={`${d.label}: ${d.value}`}
                  onMouseEnter={(e) => show(e, d)}
                  onFocus={(e) => show(e, d)}
                  onBlur={() => setTip(null)}
                  className="w-full rounded-t-[4px] bg-[var(--series-1)] outline-none transition-colors hover:bg-[var(--series-1-hover)] focus:bg-[var(--series-1-hover)]"
                  style={{ height: d.value ? `${Math.max(2, (d.value / niceTop) * 100)}%` : 0 }}
                />
              </div>
            ))}
          </div>
        </div>
        <div className="mt-1 flex gap-[2px]">
          {data.map((d, i) => (
            <span key={d.label} className="flex min-w-0 flex-1 justify-center overflow-visible whitespace-nowrap text-[10px] muted">
              {i % tickEvery === 0 ? d.label : ''}
            </span>
          ))}
        </div>
        <Tooltip tip={tip} />
      </div>
    </ChartFrame>
  )
}
