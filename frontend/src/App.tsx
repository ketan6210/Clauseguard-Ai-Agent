import { FormEvent, useState } from 'react'
import { askQuestion, getReport, updateDecision, uploadReview } from './api'
import type { QuestionResponse, ReviewResponse } from './types'

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [review, setReview] = useState<ReviewResponse | null>(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<QuestionResponse | null>(null)
  const [report, setReport] = useState<object | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

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
      setReview({ ...review, findings: review.findings.map(item => item.id === findingId ? { ...item, status: decision } : item) })
    } catch { setError('The reviewer decision could not be saved.') }
  }

  async function ask(event: FormEvent) {
    event.preventDefault(); if (!review || !question.trim()) return
    setBusy(true); setError('')
    try { setAnswer(await askQuestion(review.review_id, question)) }
    catch { setError('The question could not be answered.') }
    finally { setBusy(false) }
  }

  return <>
    <header><div className="brand"><span className="mark">CG</span><div><strong>ClauseGuard</strong><small>Contract intelligence, with evidence</small></div></div><span className="badge">Human review required</span></header>
    <main>
      <section className="hero"><p className="eyebrow">COMPLIANCE WORKBENCH</p><h1>Know what the contract <em>really</em> says.</h1><p>Review vendor contracts against company policy, trace every finding to evidence, and keep the final decision with your team.</p></section>
      <form className="upload" onSubmit={submitUpload}>
        <label><span>{file ? file.name : 'Choose a contract'}</span><small>PDF, DOCX, TXT, or Markdown · maximum 20 MB</small><input type="file" accept=".pdf,.docx,.txt,.md" onChange={e => setFile(e.target.files?.[0] || null)}/></label>
        <button disabled={!file || busy}>{busy ? 'Reviewing…' : 'Run compliance review'}</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {review && <>
        <section className="overview"><div><p className="eyebrow">REVIEW COMPLETE</p><h2>{review.filename}</h2><p>{review.summary}</p></div><div className="stat"><strong>{review.findings.length}</strong><span>findings</span></div><div className="stat"><strong>{review.clauses.length}</strong><span>clauses</span></div><div className="stat"><strong>{review.contract_type}</strong><span>document type</span></div></section>
        <div className="section-title"><div><p className="eyebrow">PRIORITIZED REVIEW</p><h2>Findings</h2></div></div>
        <section className="findings">{review.findings.map(finding => <article className="finding" key={finding.id}>
          <div className="finding-head"><span className={`risk ${finding.risk_level.toLowerCase()}`}>{finding.risk_level}</span><span className="confidence">{Math.round(finding.confidence * 100)}% confidence</span><span className={`status ${finding.status}`}>{finding.status}</span></div>
          <h3>{finding.title}</h3><p>{finding.explanation}</p><blockquote>{finding.contract_excerpt}</blockquote><p className="action"><strong>Recommended:</strong> {finding.recommended_action}</p>
          {finding.evidence.map(item => <details key={item.source_id}><summary>{item.title} · {item.section}</summary><p>{item.text}</p><small>Policy ID {item.source_id} · relevance {Math.round(item.score * 100)}%</small></details>)}
          <div className="decisions"><button onClick={() => decide(finding.id, 'approved')} disabled={finding.status !== 'pending'}>Approve finding</button><button className="reject" onClick={() => decide(finding.id, 'rejected')} disabled={finding.status !== 'pending'}>Reject</button></div>
        </article>)}</section>
        <section className="ask"><p className="eyebrow">CITED Q&A</p><h2>Ask about this contract</h2><form onSubmit={ask}><input value={question} onChange={e => setQuestion(e.target.value)} placeholder="What are the breach notification obligations?"/><button disabled={busy}>Ask</button></form>{answer && <div className="answer"><p>{answer.answer}</p>{answer.citations.map(c => <small key={c.source_id}>{c.title} — {c.section}</small>)}</div>}</section>
        <section className="report"><button onClick={async () => setReport(await getReport(review.review_id))}>Generate JSON report</button>{report && <pre>{JSON.stringify(report, null, 2)}</pre>}</section>
      </>}
    </main><footer>ClauseGuard assists legal and compliance reviewers. It does not replace legal counsel.</footer>
  </>
}
export default App
