import type { Health, IngestResult, RenderResult, VideoData } from '../types'

async function request<T>(url: string, init: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = body.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
          ? `${detail[0].loc?.join('.') ?? ''}: ${detail[0].msg}`
          : `HTTP ${res.status} ${res.statusText}`
    throw new Error(msg)
  }
  return res.json()
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export function uploadVideo(file: File): Promise<IngestResult> {
  const form = new FormData()
  form.append('file', file)
  return request('/api/ingest/upload', { method: 'POST', body: form })
}

export const downloadVideo = (url: string): Promise<IngestResult> => request('/api/ingest/download', json({ url }))

export const processVideo = (videoId: string, language: string | null): Promise<VideoData> =>
  request('/api/process', json({ video_id: videoId, language }))

export const renderVideo = (data: VideoData): Promise<RenderResult> => request('/api/render', json(data))

export const mediaUrl = (videoId: string) => `/api/media/${videoId}`

export async function getHealth(): Promise<Health> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
