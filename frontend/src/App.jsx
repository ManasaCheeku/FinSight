import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const ENDPOINTS = {
  summary: '/metrics/summary',
  revenue: '/metrics/revenue',
  expenses: '/metrics/expenses',
  cashflow: '/metrics/cashflow',
  anomalies: '/anomalies',
  forecast: '/forecast',
  vendors: '/vendors',
  invoices: '/invoices',
  budgets: '/budgets',
}

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: '⌂' },
  { id: 'performance', label: 'Performance', icon: '↗' },
  { id: 'risk', label: 'Risk signals', icon: '◈' },
  { id: 'operations', label: 'Operations', icon: '▦' },
  { id: 'assistant', label: 'AI assistant', icon: '✦' },
]

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function valueFrom(value, keys) {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return value
  if (typeof value === 'string' && value.trim() !== '' && !Number.isNaN(Number(value))) return Number(value)
  if (typeof value === 'object') {
    for (const key of keys) {
      if (value[key] !== null && value[key] !== undefined) return valueFrom(value[key], keys)
    }
  }
  return null
}

function listFrom(payload, keys) {
  if (Array.isArray(payload)) return payload
  if (!payload || typeof payload !== 'object') return []
  for (const key of keys) {
    if (Array.isArray(payload[key])) return payload[key]
  }
  return []
}

function formatINR(value, compact = false) {
  const number = valueFrom(value, ['amount', 'total', 'value'])
  if (number === null || !Number.isFinite(number)) return '—'
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    notation: compact && Math.abs(number) >= 100000 ? 'compact' : 'standard',
    maximumFractionDigits: compact && Math.abs(number) >= 100000 ? 1 : 0,
  }).format(number)
}

function formatNumber(value) {
  const number = valueFrom(value, [])
  return number === null ? '—' : new Intl.NumberFormat('en-IN').format(number)
}

function monthLabel(row) {
  if (!row) return ''
  const month = Number(row.month)
  return month >= 1 && month <= 12 ? MONTH_NAMES[month - 1] : String(row.period || row.month || '')
}

function initials(name) {
  return String(name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
}

function StatusPill({ children, tone = 'neutral' }) {
  return <span className={`status-pill status-${tone}`}>{children}</span>
}

function EmptyState({ title = 'No data available', detail = 'This view will populate when the API returns records.' }) {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">∅</span>
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  )
}

function LoadingState({ label = 'Loading financial intelligence…' }) {
  return (
    <div className="loading-state" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  )
}

function Trend({ value, inverse = false }) {
  const number = valueFrom(value, ['growth_pct'])
  if (number === null) return <span className="trend trend-neutral">No comparison</span>
  const positive = inverse ? number <= 0 : number >= 0
  return <span className={`trend ${positive ? 'trend-positive' : 'trend-negative'}`}>{number >= 0 ? '↑' : '↓'} {Math.abs(number).toFixed(1)}%</span>
}

function IconLogo() {
  return (
    <div className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 42 42" role="presentation">
        <path d="M9 28.5 17.5 20l5.1 5.1L33 14.5" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M27 14.5h6v6" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

function Sidebar({ active, onNavigate, open, onClose }) {
  return (
    <>
      {open && <button className="sidebar-backdrop" type="button" aria-label="Close navigation" onClick={onClose} />}
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <IconLogo />
          <div><strong>FinSight</strong><span>Financial intelligence</span></div>
          <button className="icon-button sidebar-close" type="button" aria-label="Close navigation" onClick={onClose}>×</button>
        </div>
        <div className="workspace-switcher">
          <span className="workspace-avatar">F</span>
          <span><strong>Finance workspace</strong><small>Connected dataset</small></span>
          <span className="chevron" aria-hidden="true">⌄</span>
        </div>
        <nav aria-label="Primary navigation">
          <span className="nav-label">Workspace</span>
          {NAV_ITEMS.map((item) => (
            <button key={item.id} className={`nav-item ${active === item.id ? 'nav-active' : ''}`} type="button" onClick={() => onNavigate(item.id)}>
              <span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>
              {item.id === 'risk' && <span className="nav-dot" aria-label="Risk signals available" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="data-health"><span className="health-dot" /><span><strong>API connected</strong><small>{API_BASE.replace(/^https?:\/\//, '')}</small></span></div>
          <button className="nav-item" type="button"><span className="nav-icon" aria-hidden="true">⚙</span><span>Settings</span></button>
          <p className="sidebar-footnote">Built for confident decisions.<br />Data stays explainable.</p>
        </div>
      </aside>
    </>
  )
}

function Header({ datasetLabel, lastUpdated, loading, onRefresh, onMenu }) {
  return (
    <header className="topbar">
      <div className="topbar-title">
        <button className="icon-button menu-button" type="button" aria-label="Open navigation" onClick={onMenu}>☰</button>
        <div><p className="eyebrow">Financial command center</p><h1>Good morning, <span>Finance team</span></h1></div>
      </div>
      <div className="topbar-actions">
        <div className="dataset-label"><span className="live-dot" /> <span>{datasetLabel || 'Dataset unavailable'}</span></div>
        <span className="last-updated">{lastUpdated ? `Updated ${lastUpdated}` : 'Not synced'}</span>
        <button className="refresh-button" type="button" onClick={onRefresh} disabled={loading}><span className={loading ? 'refresh-icon spinning' : 'refresh-icon'}>↻</span> Refresh</button>
        <button className="profile-button" type="button" aria-label="Finance team profile">FT</button>
      </div>
    </header>
  )
}

function KpiCard({ label, value, detail, trend, icon, tone = 'violet', inverse = false }) {
  return (
    <article className={`kpi-card kpi-${tone}`}>
      <div className="kpi-head"><span>{label}</span><span className="kpi-icon" aria-hidden="true">{icon}</span></div>
      <strong className="kpi-value">{value}</strong>
      <div className="kpi-foot"><span>{detail}</span>{trend !== undefined && <Trend value={trend} inverse={inverse} />}</div>
    </article>
  )
}

function PerformanceChart({ revenue, expenses }) {
  const rows = useMemo(() => {
    const map = new Map()
    listFrom(revenue, ['monthly_revenue', 'revenue']).forEach((row) => {
      const key = `${row.year || ''}-${row.month || row.period || ''}`
      map.set(key, { ...map.get(key), ...row, revenue: valueFrom(row.revenue ?? row.amount, []) || 0 })
    })
    listFrom(expenses, ['monthly_expenses', 'expenses']).forEach((row) => {
      const key = `${row.year || ''}-${row.month || row.period || ''}`
      map.set(key, { ...map.get(key), ...row, expenses: valueFrom(row.expenses ?? row.amount, []) || 0 })
    })
    return [...map.values()].sort((a, b) => `${a.year}-${a.month}`.localeCompare(`${b.year}-${b.month}`)).slice(-8)
  }, [revenue, expenses])
  const max = Math.max(...rows.flatMap((row) => [row.revenue || 0, row.expenses || 0]), 0)
  const chartHeight = 180
  const chartWidth = 680
  const points = (key) => rows.map((row, index) => `${(index / Math.max(rows.length - 1, 1)) * chartWidth},${chartHeight - ((row[key] || 0) / (max || 1)) * 150}`).join(' ')
  return (
    <div className="chart-wrap">
      {!rows.length ? <EmptyState title="No performance history" /> : (
        <>
          <div className="chart-legend"><span><i className="legend-dot legend-revenue" />Revenue <b>Actual</b></span><span><i className="legend-dot legend-expense" />Expenses <b>Actual</b></span></div>
          <svg className="line-chart" viewBox={`0 0 ${chartWidth} ${chartHeight + 26}`} role="img" aria-label="Monthly revenue and expenses">
            {[0, 1, 2, 3].map((line) => <line key={line} x1="0" x2={chartWidth} y1={15 + line * 50} y2={15 + line * 50} className="grid-line" />)}
            <polyline points={points('revenue')} className="chart-line chart-line-revenue" />
            <polyline points={points('expenses')} className="chart-line chart-line-expenses" />
            {rows.map((row, index) => {
              const x = (index / Math.max(rows.length - 1, 1)) * chartWidth
              return <text key={`${row.year}-${row.month}-${index}`} x={x} y="205" textAnchor={index === 0 ? 'start' : index === rows.length - 1 ? 'end' : 'middle'}>{monthLabel(row)}</text>
            })}
          </svg>
          <div className="chart-summary"><span><small>Latest revenue</small><strong>{formatINR(rows.at(-1)?.revenue, true)}</strong></span><span><small>Latest expenses</small><strong>{formatINR(rows.at(-1)?.expenses, true)}</strong></span><span><small>Period net</small><strong>{formatINR(rows.reduce((sum, row) => sum + (row.revenue || 0) - (row.expenses || 0), 0), true)}</strong></span></div>
        </>
      )}
    </div>
  )
}

function CashflowCard({ cashflow, revenue, expenses }) {
  const balance = valueFrom(cashflow?.current_cash_balance, [])
  const net = valueFrom(cashflow?.net_cash_flow, [])
  const margin = valueFrom(cashflow?.profit_margin?.profit_margin_pct ?? cashflow?.profit_margin_pct, [])
  const rows = useMemo(() => {
    const rev = listFrom(revenue, ['monthly_revenue', 'revenue'])
    const exp = listFrom(expenses, ['monthly_expenses', 'expenses'])
    return rev.map((row, index) => ({ ...row, net: (valueFrom(row.revenue ?? row.amount, []) || 0) - (valueFrom(exp[index]?.expenses ?? exp[index]?.amount, []) || 0) })).slice(-6)
  }, [revenue, expenses])
  const peak = Math.max(...rows.map((row) => Math.abs(row.net)), 0)
  return (
    <article className="panel cashflow-panel" id="cashflow">
      <div className="panel-heading"><div><p className="eyebrow">Liquidity</p><h2>Cash flow health</h2></div><StatusPill tone={net !== null && net >= 0 ? 'success' : 'danger'}>{net !== null && net >= 0 ? 'Positive' : 'Needs attention'}</StatusPill></div>
      <div className="cashflow-balance"><span>Current cash balance</span><strong>{formatINR(balance, true)}</strong><small>Actual · cumulative transactions</small></div>
      {rows.length ? <div className="cash-bars" aria-label="Monthly net cash flow bars">{rows.map((row, index) => <div className="cash-bar-group" key={`${row.year}-${row.month}-${index}`}><div className={`cash-bar ${row.net >= 0 ? 'bar-positive' : 'bar-negative'}`} style={{ height: `${Math.max(8, Math.abs(row.net) / (peak || 1) * 80)}px` }} title={`${monthLabel(row)}: ${formatINR(row.net)}`} /><span>{monthLabel(row)}</span></div>)}</div> : <EmptyState title="No cash flow history" />}
      <div className="metric-row"><span>Net cash flow</span><strong>{formatINR(net, true)}</strong></div>
      <div className="metric-row"><span>Profit margin</span><strong>{margin === null ? '—' : `${margin.toFixed(1)}%`}</strong></div>
    </article>
  )
}

function AnomalyPanel({ anomalies }) {
  const rows = listFrom(anomalies, ['anomalies']).slice(0, 5)
  const counts = anomalies?.severity_summary || {}
  return (
    <section className="panel risk-panel" id="risk">
      <div className="panel-heading"><div><p className="eyebrow">Monitor</p><h2>Risk signals</h2></div><span className="panel-count">{formatNumber(anomalies?.total_anomalies)} detected</span></div>
      <div className="risk-summary"><span><b>{formatNumber(counts.critical || 0)}</b><small>Critical</small></span><span><b>{formatNumber(counts.high || 0)}</b><small>High</small></span><span><b>{formatNumber(counts.medium || 0)}</b><small>Medium</small></span><span><b>{formatNumber(counts.low || 0)}</b><small>Low</small></span></div>
      {!rows.length ? <EmptyState title="No risk signals" detail="No deterministic anomalies were returned for this dataset." /> : <div className="anomaly-list">{rows.map((row, index) => <div className="anomaly-item" key={`${row.type}-${row.entity}-${index}`}><span className={`severity-icon severity-${row.severity || 'low'}`} aria-hidden="true">{row.severity === 'critical' || row.severity === 'high' ? '!' : 'i'}</span><div><div className="anomaly-title"><strong>{row.entity || row.type || 'Risk indicator'}</strong><StatusPill tone={row.severity === 'critical' || row.severity === 'high' ? 'danger' : 'warning'}>{row.severity || 'review'}</StatusPill></div><p>{row.explanation || 'A deterministic risk indicator requires review.'}</p><small>{row.period || 'Historical signal'} · {row.deviation_pct !== undefined ? `${row.deviation_pct}% deviation` : 'Actual'}</small></div></div>)}</div>}
      {anomalies?.disclaimer && <p className="disclaimer">{anomalies.disclaimer}</p>}
    </section>
  )
}

function ForecastPanel({ forecast }) {
  const forecasts = listFrom(forecast, ['forecasts']).sort((a, b) => Number(a.horizon_days) - Number(b.horizon_days))
  return (
    <section className="panel forecast-panel" id="forecast">
      <div className="panel-heading"><div><p className="eyebrow">Planning horizon</p><h2>Cash flow outlook</h2></div><StatusPill tone="forecast">Forecast · not actual</StatusPill></div>
      <div className="forecast-lead"><span>Opening balance</span><strong>{formatINR(forecast?.opening_cash_balance, true)}</strong><p>{forecast?.method || 'Forecast methodology returned by API.'}</p></div>
      {!forecasts.length ? <EmptyState title="No forecast available" /> : <div className="forecast-grid">{forecasts.map((item) => <div className="forecast-card" key={item.horizon_days}><span>{item.horizon_days} days</span><strong>{formatINR(item.projected_cash_balance, true)}</strong><small>Projected balance</small><div className="forecast-meta"><span className={item.projected_net_cash_flow >= 0 ? 'text-success' : 'text-danger'}>{formatINR(item.projected_net_cash_flow, true)} net</span><span>{item.uncertainty_pct !== undefined ? `${item.uncertainty_pct}% uncertainty` : 'Forecast'}</span></div></div>)}</div>}
      {forecast?.disclaimer && <p className="disclaimer">{forecast.disclaimer}</p>}
    </section>
  )
}

function VendorsPanel({ vendors }) {
  const rows = listFrom(vendors, ['vendors'])
  return (
    <section className="panel table-panel" id="operations">
      <div className="panel-heading"><div><p className="eyebrow">Partners</p><h2>Vendor directory</h2></div><span className="panel-count">{formatNumber(vendors?.total ?? rows.length)} vendors</span></div>
      {!rows.length ? <EmptyState title="No vendors found" /> : <div className="table-scroll"><table><thead><tr><th>Vendor</th><th>Category</th><th>Payment terms</th><th>Contact</th></tr></thead><tbody>{rows.slice(0, 6).map((row) => <tr key={row.id}><td><span className="entity-cell"><span className="avatar">{initials(row.name)}</span><strong>{row.name || 'Unnamed vendor'}</strong></span></td><td>{row.category || '—'}</td><td>{row.payment_terms || '—'}</td><td className="muted">{row.contact_email || '—'}</td></tr>)}</tbody></table></div>}
    </section>
  )
}

function InvoicesPanel({ invoices, vendors }) {
  const rows = listFrom(invoices, ['invoices'])
  const vendorMap = useMemo(() => new Map(listFrom(vendors, ['vendors']).map((vendor) => [vendor.id, vendor.name])), [vendors])
  return (
    <section className="panel table-panel">
      <div className="panel-heading"><div><p className="eyebrow">Payables</p><h2>Invoice watchlist</h2></div><span className="panel-count">{formatNumber(invoices?.total ?? rows.length)} invoices</span></div>
      {!rows.length ? <EmptyState title="No invoices found" /> : <div className="table-scroll"><table><thead><tr><th>Invoice</th><th>Vendor</th><th>Amount</th><th>Due date</th><th>Status</th></tr></thead><tbody>{rows.slice(0, 6).map((row) => <tr key={row.id}><td><strong>{row.invoice_number || `Invoice #${row.id}`}</strong><small className="table-subtitle">{row.description || 'Invoice record'}</small></td><td>{vendorMap.get(row.vendor_id) || `Vendor #${row.vendor_id}`}</td><td><strong>{formatINR(row.amount)}</strong></td><td>{row.due_date ? new Date(row.due_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}</td><td><StatusPill tone={String(row.status).toLowerCase() === 'paid' ? 'success' : String(row.status).toLowerCase() === 'overdue' ? 'danger' : 'warning'}>{row.status || 'Unknown'}</StatusPill></td></tr>)}</tbody></table></div>}
    </section>
  )
}

function BudgetsPanel({ budgets }) {
  const rows = listFrom(budgets, ['budgets'])
  return (
    <section className="panel budget-panel">
      <div className="panel-heading"><div><p className="eyebrow">Controls</p><h2>Budget pulse</h2></div><span className="panel-count">{formatNumber(budgets?.total ?? rows.length)} lines</span></div>
      {!rows.length ? <EmptyState title="No budget data" /> : <div className="budget-list">{rows.slice(0, 5).map((row, index) => { const planned = valueFrom(row.planned_amount ?? row.planned, []); const actual = valueFrom(row.actual_amount ?? row.actual, []); const progress = planned ? Math.min((actual / planned) * 100, 100) : 0; const over = planned !== null && actual !== null && actual > planned; return <div className="budget-row" key={row.id || `${row.category}-${index}`}><div className="budget-row-head"><span><strong>{row.category || 'Uncategorised'}</strong><small>{row.year || '—'} · {row.month || '—'}</small></span><span className={over ? 'text-danger' : 'text-success'}>{formatINR(actual, true)} <em>/ {formatINR(planned, true)}</em></span></div><div className="progress-track"><span className={over ? 'progress-over' : ''} style={{ width: `${progress}%` }} /></div></div> })}</div>}
    </section>
  )
}

function Assistant({ onAsk, messages, loading }) {
  const [question, setQuestion] = useState('')
  const submit = async (event) => {
    event.preventDefault()
    if (!question.trim() || loading) return
    const next = question
    setQuestion('')
    await onAsk(next)
  }
  return (
    <section className="panel assistant-panel" id="assistant">
      <div className="assistant-header"><div className="assistant-avatar">✦</div><div><p className="eyebrow">Grounded intelligence</p><h2>Ask FinSight</h2><span>Answers cite your connected financial data</span></div><StatusPill tone="success">Online</StatusPill></div>
      <div className="chat-messages" aria-live="polite">
        {!messages.length && <div className="assistant-welcome"><strong>What would you like to understand?</strong><p>Ask about cash flow, anomalies, expenses, vendors, or your forecast.</p><div className="suggestion-list"><button type="button" onClick={() => setQuestion('What is driving our current cash position?')}>What is driving our current cash position?</button><button type="button" onClick={() => setQuestion('Which risk signals should I review first?')}>Which risk signals should I review first?</button></div></div>}
        {messages.map((message, index) => <div className={`message message-${message.role}`} key={`${message.role}-${index}`}><span className="message-avatar">{message.role === 'user' ? 'You' : '✦'}</span><div><p>{message.content}</p>{message.role === 'assistant' && message.tools?.length > 0 && <small>Sources: {message.tools.join(', ')}</small>}</div></div>)}
        {loading && <div className="message message-assistant"><span className="message-avatar">✦</span><div className="typing"><i /><i /><i /></div></div>}
      </div>
      <form className="chat-form" onSubmit={submit}><label className="sr-only" htmlFor="assistant-question">Ask a financial question</label><input id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question about your finances…" maxLength={4000} /><button type="submit" aria-label="Send question" disabled={!question.trim() || loading}>↑</button></form>
      <small className="chat-disclaimer">AI responses are grounded in API data and should be reviewed before action.</small>
    </section>
  )
}

function App() {
  const [data, setData] = useState({})
  const [errors, setErrors] = useState([])
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState('')
  const [active, setActive] = useState('overview')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [aiLoading, setAiLoading] = useState(false)

  const loadDashboard = useCallback(async () => {
    setLoading(true)
    const entries = Object.entries(ENDPOINTS)
    const results = await Promise.all(entries.map(async ([key, endpoint]) => {
      try {
        const response = await fetch(`${API_BASE}${endpoint}`)
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`)
        return [key, await response.json(), null]
      } catch (error) {
        return [key, null, `${endpoint}: ${error.message}`]
      }
    }))
    const nextData = {}
    const nextErrors = []
    results.forEach(([key, payload, error]) => { if (payload !== null) nextData[key] = payload; if (error) nextErrors.push(error) })
    setData(nextData)
    setErrors(nextErrors)
    setLastUpdated(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }))
    setLoading(false)
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(() => { loadDashboard() }, 0)
    return () => window.clearTimeout(timer)
  }, [loadDashboard])

  const navigate = (id) => {
    setActive(id)
    setSidebarOpen(false)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const askAssistant = async (question) => {
    const userMessage = { role: 'user', content: question }
    setMessages((current) => [...current, userMessage])
    setAiLoading(true)
    try {
      const response = await fetch(`${API_BASE}/ai/ask`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, conversation_history: messages.map(({ role, content }) => ({ role, content })) }) })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || `${response.status} ${response.statusText}`)
      setMessages((current) => [...current, { role: 'assistant', content: payload.answer || payload.recommendation || 'The assistant returned no narrative answer.', tools: payload.tools_used }])
    } catch (error) {
      setMessages((current) => [...current, { role: 'assistant', content: `I couldn’t reach the financial assistant. ${error.message}` }])
    } finally {
      setAiLoading(false)
    }
  }

  const summary = data.summary || {}
  const datasetLabel = summary.dataset_label || data.revenue?.dataset_label || data.forecast?.dataset_label || ''
  const revenueGrowth = summary.revenue_growth?.growth_pct ?? data.revenue?.revenue_growth?.growth_pct
  const expenseGrowth = summary.expense_growth?.growth_pct ?? data.expenses?.expense_growth?.growth_pct
  const hasAnyData = Object.keys(data).length > 0

  return (
    <div className="app-shell">
      <Sidebar active={active} onNavigate={navigate} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="main-content">
        <Header datasetLabel={datasetLabel} lastUpdated={lastUpdated} loading={loading} onRefresh={loadDashboard} onMenu={() => setSidebarOpen(true)} />
        {errors.length > 0 && <div className="api-alert" role="status"><span aria-hidden="true">!</span><div><strong>{hasAnyData ? 'Some data could not be refreshed' : 'Could not connect to the FinSight API'}</strong><small>{errors[0]} · Check that the backend is running at {API_BASE}</small></div><button type="button" onClick={loadDashboard}>Try again</button></div>}
        {loading && !hasAnyData ? <LoadingState /> : <div className="dashboard-content">
          <section className="welcome-row" id="overview"><div><p className="eyebrow">Portfolio overview</p><h2>See the signal in your numbers.</h2><p className="welcome-copy">A clear view of performance, liquidity, and what needs your attention next.</p></div><div className="actual-badge"><span className="actual-dot" />Actual data <small>from connected API</small></div></section>
          <section className="kpi-grid" aria-label="Key performance indicators">
            <KpiCard label="Total revenue" value={formatINR(summary.total_revenue, true)} detail="Lifetime actual" trend={revenueGrowth} icon="↗" tone="violet" />
            <KpiCard label="Total expenses" value={formatINR(summary.total_expenses, true)} detail="Lifetime actual" trend={expenseGrowth} icon="↘" tone="peach" inverse />
            <KpiCard label="Net cash flow" value={formatINR(summary.net_cash_flow, true)} detail="Revenue less expenses" icon="≈" tone="mint" />
            <KpiCard label="Profit margin" value={summary.profit_margin_pct === null || summary.profit_margin_pct === undefined ? '—' : `${Number(summary.profit_margin_pct).toFixed(1)}%`} detail="Actual performance" icon="%" tone="blue" />
          </section>
          <section className="split-layout performance-layout" id="performance"><article className="panel performance-panel"><div className="panel-heading"><div><p className="eyebrow">Performance</p><h2>Revenue & expenses</h2></div><StatusPill tone="actual">Actual</StatusPill></div><PerformanceChart revenue={data.revenue} expenses={data.expenses} /></article><CashflowCard cashflow={data.cashflow} revenue={data.revenue} expenses={data.expenses} /></section>
          <section className="split-layout risk-layout"><AnomalyPanel anomalies={data.anomalies} /><ForecastPanel forecast={data.forecast} /></section>
          <section className="split-layout operations-layout"><VendorsPanel vendors={data.vendors} /><BudgetsPanel budgets={data.budgets} /></section>
          <InvoicesPanel invoices={data.invoices} vendors={data.vendors} />
          <Assistant onAsk={askAssistant} messages={messages} loading={aiLoading} />
        </div>}
        <footer className="app-footer"><span>FinSight <b>·</b> Financial intelligence platform</span><span>All amounts displayed in INR <b>·</b> {datasetLabel || 'Connected API data'}</span></footer>
      </main>
    </div>
  )
}

export default App
