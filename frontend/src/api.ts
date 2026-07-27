import axios from 'axios'
import type { QuestionResponse, ReviewResponse } from './types'

const client = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000', timeout: 180000 })

export async function uploadReview(file: File): Promise<ReviewResponse> {
  const body = new FormData(); body.append('file', file)
  return (await client.post('/reviews/upload', body)).data
}
export async function askQuestion(reviewId: string, question: string): Promise<QuestionResponse> {
  return (await client.post(`/reviews/${reviewId}/ask`, { question })).data
}
export async function updateDecision(reviewId: string, findingId: string, decision: 'approved'|'rejected', comment = '') {
  return (await client.post(`/reviews/${reviewId}/decision`, { finding_id: findingId, decision, comment })).data
}
export async function getReport(reviewId: string): Promise<ReviewResponse> {
  return (await client.get(`/reviews/${reviewId}/report`)).data
}
