export interface IngestResult {
  video_id: string
  filename: string
  path: string
  size_bytes: number
  source: string
}

async function handle(res: Response): Promise<IngestResult> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${res.status}`)
  }
  return res.json()
}

export async function uploadVideo(file: File): Promise<IngestResult> {
  const form = new FormData()
  form.append('file', file)
  return handle(await fetch('/api/ingest/upload', { method: 'POST', body: form }))
}

export async function downloadVideo(url: string): Promise<IngestResult> {
  return handle(
    await fetch('/api/ingest/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    }),
  )
}
