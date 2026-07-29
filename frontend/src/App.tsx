import { FormEvent, useEffect, useMemo, useState } from 'react'
import { askQuestion, getCapabilities, getReport, updateDecision, uploadReview, validateFinding } from './api'
import type { Capabilities, QuestionResponse, ReviewResponse } from './types'

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [review, setReview] = useState<ReviewResponse | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<QuestionResponse | null>(null)
  const [report, setReport] = useState<object | null>(null)
  const [severityFilter, setSeverityFilter] = useState('All')
  const [verificationFilter, setVerificationFilter] = useState('All')
  const [findingSearch, setFindingSearch] = useState('')
  const [sortBy, setSortBy] = useState('priority')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [validationLabels, setValidationLabels] = useState<Record<string, string>>({})
  const matchBand = (score: number) => score >= 0.85 ? 'Strong' : score >= 0.7 ? 'Moderate' : 'Weak'
  const visibleFindings = useMemo(() => {
    if (!review) return []
    const query = findingSearch.trim().toLowerCase()
    return review.findings
      .filter(finding => severityFilter === 'All' || finding.risk_level === severityFilter)
      .filter(finding => verificationFilter === 'All' || finding.verification === verificationFilter)
      .filter(finding => !query || `${finding.title} ${finding.explanation} ${finding.contract_excerpt}`.toLowerCase().includes(query))
      .sort((left, right) => sortBy === 'evidence'
        ? right.combined_score - left.combined_score
        : sortBy === 'severity'
          ? ({ Critical: 4, High: 3, Medium: 2, Low: 1 }[right.risk_level] - { Critical: 4, High: 3, Medium: 2, Low: 1 }[left.risk_level])
          : right.priority_score - left.priority_score)
  }, [review, severityFilter, verificationFilter, findingSearch, sortBy])
  useEffect(() => { getCapabilities().then(setCapabilities).catch(() => setCapabilities(null)) }, [])

  async function submitUpload(event: FormEvent) {
    event.preventDefault(); if (!file) return
    setBusy(true); setError(''); setReview(null); setAnswer(null); setReport(null)
    try { setReview(await uploadReview(file)) }
    catch (err: any) { setError(err.response?.data?.detail || 'The review could not be completed.') }
    finally { setBusy(false) }
  }

  async function decide(findingId: string, decision: 'approved'|'rejected') {
    if (!review) return
    try {
      await updateDecision(review.review_id, findingId, decision)
      setReview({ ...review, findings: review.findings.map(item => item.id === findingId ? { ...item, status: decision } : item), metrics: { ...review.metrics, pending_human_review: Math.max(0, review.metrics.pending_human_review - 1) } })
    } catch { setError('The reviewer decision could not be saved.') }
  }

  async function ask(event: FormEvent) {
    event.preventDefault(); if (!review || !question.trim()) return
    setBusy(true); setError('')
    try { setAnswer(await askQuestion(review.review_id, question)) }
    catch { setError('The question could not be answered.') }
    finally { setBusy(false) }
  }

  async function labelFinding(findingId: string, label: 'valid'|'invalid'|'uncertain') {
    if (!review) return
    try {
      await validateFinding(review.review_id, findingId, label)
      setValidationLabels(current => ({ ...current, [findingId]: label }))
    } catch { setError('The accuracy label could not be saved.') }
  }

  return <>
    <header><div className="brand"><span className="mark">CG</span><div><strong>ClauseGuard</strong><small>Contract intelligence, with evidence</small></div></div><div><span className={`badge ${capabilities?.ollama.model_available ? 'online' : 'offline'}`}>{capabilities?.ollama.model_available ? `${capabilities.ollama.model} online` : 'Evidence fallback mode'}</span> <span className="badge">Human review required</span></div></header>
    <main>
      <section className="hero"><p className="eyebrow">COMPLIANCE WORKBENCH</p><h1>Know what the contract <em>really</em> says.</h1><p>Review vendor contracts against company policy, trace every finding to evidence, and keep the final decision with your team.</p></section>
      <form className="upload" onSubmit={submitUpload}>
        <label><span>{file ? file.name : 'Choose a contract'}</span><small>PDF, DOCX, TXT, or Markdown · maximum 20 MB</small><input type="file" accept=".pdf,.docx,.txt,.md" onChange={e => setFile(e.target.files?.[0] || null)}/></label>
        <button disabled={!file || busy}>{busy ? 'Reviewing…' : 'Run compliance review'}</button>
      </form>
      {busy && !review && <p className="processing">Parsing clauses, retrieving policy evidence, running rules, and validating findings with local Qwen…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {review && <>
        <section className="overview"><div><p className="eyebrow">REVIEW COMPLETE</p><h2>{review.filename}</h2><p>{review.summary}</p></div><div className="stat"><strong>{review.findings.length}</strong><span>findings</span></div><div className="stat"><strong>{review.clauses.length}</strong><span>clauses</span></div><div className="stat"><strong>{review.contract_type}</strong><span>document type</span></div></section>
        {/* Contract risk and evidence health are deliberately separate metrics. */}
        <section className="analytics">
          <article className={`score-card ${review.metrics.overall_risk_band.toLowerCase()}`}><small>Overall contract risk</small><strong>{Math.round(review.metrics.overall_risk_score)}</strong><span>{review.metrics.overall_risk_band}</span><p>Combines the strongest finding, top-five priorities, and risk prevalence.</p><details><summary>Risk score inputs</summary>{Object.entries(review.metrics.risk_score_factors).map(([name, value]) => <small key={name}>{name.replace(/_/g, ' ')}: {Math.round(value)}</small>)}</details></article>
          <article className="score-card quality"><small>Evidence health</small><strong>{Math.round(review.metrics.evidence_health_score)}</strong><span>out of 100</span><p>Evidence support and runtime coverage—not measured legal accuracy.</p></article>
          <article className="metric-list"><strong>Risk distribution</strong>{['Critical', 'High', 'Medium', 'Low'].map(level => <span key={level}>{level}<b>{review.metrics.severity_counts[level] || 0}</b></span>)}</article>
          <article className="metric-list"><strong>Evidence coverage</strong><span>Policy RAG<b>{Math.round(review.metrics.policy_coverage * 100)}%</b></span><span>Qwen assessed<b>{Math.round(review.metrics.qwen_assessment_coverage * 100)}%</b></span><span>Qwen confirmed<b>{Math.round(review.metrics.qwen_verification_coverage * 100)}%</b></span><span>Pending review<b>{review.metrics.pending_human_review}</b></span></article>
        </section>
        <div className="section-title"><div><p className="eyebrow">PRIORITIZED REVIEW</p><h2>Findings <small>({visibleFindings.length})</small></h2></div><div className="filters"><input value={findingSearch} onChange={e => setFindingSearch(e.target.value)} placeholder="Search findings"/><label>Severity <select value={severityFilter} onChange={e => setSeverityFilter(e.target.value)}><option>All</option><option>Critical</option><option>High</option><option>Medium</option><option>Low</option></select></label><label>Verification <select value={verificationFilter} onChange={e => setVerificationFilter(e.target.value)}><option value="All">All</option><option value="rule_and_qwen">Rule + Qwen</option><option value="rules_only">Rules only</option><option value="qwen_only">Qwen only</option><option value="needs_review">Disagreement</option></select></label><label>Sort <select value={sortBy} onChange={e => setSortBy(e.target.value)}><option value="priority">Priority</option><option value="severity">Risk impact</option><option value="evidence">Evidence score</option></select></label></div></div>
        <section className="findings">{visibleFindings.length === 0 && <p className="empty-state">No findings match the current filters.</p>}{visibleFindings.map(finding => <article className="finding" key={finding.id}>
          <div className="finding-head"><span className={`priority ${finding.priority_band.toLowerCase()}`}>Priority: {finding.priority_band} {Math.round(finding.priority_score)}</span><span className={`risk ${finding.risk_level.toLowerCase()}`}>Impact: {finding.risk_level}</span><span className={`match ${matchBand(finding.combined_score).toLowerCase()}`}>Evidence: {Math.round(finding.combined_score * 100)}%</span><span className={`status ${finding.status}`}>{finding.status}</span></div>
          <h3>{finding.title}</h3><p>{finding.explanation}</p><blockquote>{finding.contract_excerpt}</blockquote><p className="action"><strong>Recommended:</strong> {finding.recommended_action}</p>
          {finding.combined_score < 0.7 && <p className="review-warning">Weak combined evidence — verify this finding manually before relying on it.</p>}
          {Object.keys(finding.confidence_factors).length > 0 && <details><summary>How is the combined score calculated?</summary>{Object.entries(finding.confidence_factors).map(([name, value]) => <small key={name}>{name.replace(/_/g, ' ')}: signal {Math.round(value * 100)}% · contributes {Math.round((finding.score_contributions[name] || 0) * 100)} points · {finding.signal_status[name] || 'available'}</small>)}<small>Pipeline {finding.pipeline_version} · policy {finding.policy_version} · {finding.retrieval_mode}</small></details>}
          {finding.evidence.map(item => <details key={item.source_id}><summary>{item.title} · {item.section}</summary><p>{item.text}</p><small>Policy ID {item.source_id} · retrieval similarity {Math.round(item.score * 100)}% (similarity alone does not prove a violation)</small></details>)}
          <div className="decisions"><button onClick={() => decide(finding.id, 'approved')} disabled={finding.status !== 'pending'}>Approve finding</button><button className="reject" onClick={() => decide(finding.id, 'rejected')} disabled={finding.status !== 'pending'}>Reject</button></div>
          {/* Accuracy labels calibrate detection quality; approve/reject remains a workflow choice. */}
          <div className="accuracy-labels"><small>Was this detection factually correct?</small><button className={validationLabels[finding.id] === 'valid' ? 'selected' : ''} onClick={() => labelFinding(finding.id, 'valid')}>Valid</button><button className={validationLabels[finding.id] === 'invalid' ? 'selected' : ''} onClick={() => labelFinding(finding.id, 'invalid')}>Invalid</button><button className={validationLabels[finding.id] === 'uncertain' ? 'selected' : ''} onClick={() => labelFinding(finding.id, 'uncertain')}>Uncertain</button></div>
        </article>)}</section>
        <section className="ask"><p className="eyebrow">LOCAL AI · RAG-GROUNDED</p><h2>Ask Qwen about this contract</h2><p>Answers use the clauses and company policies retrieved for this review. No paid API key is used.</p><form onSubmit={ask}><input value={question} onChange={e => setQuestion(e.target.value)} placeholder="What are the breach notification obligations?"/><button disabled={busy}>{busy ? 'Asking Qwen…' : 'Ask local AI'}</button></form>{answer && <div className="answer"><small>Answer mode: {answer.generation_mode === 'local_llm' ? 'Local AI (Qwen)' : 'Evidence fallback'}</small>{answer.generation_mode === 'extractive_fallback' && <small>Qwen was unavailable or its answer did not pass citation validation, so ClauseGuard is showing retrieved evidence directly.</small>}<p>{answer.answer}</p>{answer.contract_citations.length > 0 && <><strong>Contract sources</strong>{answer.contract_citations.map(c => <small key={`contract-${c.source_id}`}>{c.title} — {c.section}</small>)}</>}{answer.policy_citations.length > 0 && <><strong>Policy sources</strong>{answer.policy_citations.map(c => <small key={`policy-${c.source_id}`}>{c.title} — {c.section}</small>)}</>}</div>}</section>
        <section className="report"><button onClick={async () => setReport(await getReport(review.review_id))}>Generate JSON report</button>{report && <pre>{JSON.stringify(report, null, 2)}</pre>}</section>
      </>}
    </main><footer>ClauseGuard assists legal and compliance reviewers. It does not replace legal counsel.</footer>
  </>
}
export default App
