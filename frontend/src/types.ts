export interface Evidence { source_id: string; title: string; section: string; text: string; score: number }
export interface Clause { id: string; clause_type: string; text: string; page: number; confidence: number }
export interface Finding { id: string; clause_id: string | null; title: string; risk_level: 'Low'|'Medium'|'High'|'Critical'; confidence: number; explanation: string; recommended_action: string; contract_excerpt: string; evidence: Evidence[]; status: 'pending'|'approved'|'rejected' }
export interface ReviewResponse { review_id: string; filename: string; contract_type: string; summary: string; clauses: Clause[]; findings: Finding[] }
export interface QuestionResponse { answer: string; citations: Evidence[] }
