import { useState } from 'react'
import { downloadVideo, uploadVideo, type IngestResult } from './lib/api'

export default function App() {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [items, setItems] = useState<IngestResult[]>([])

  async function run(task: () => Promise<IngestResult>) {
    setBusy(true)
    setError(null)
    try {
      const result = await task()
      setItems((prev) => [result, ...prev])
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="min-h-screen bg-neutral-950 p-6 text-neutral-100">
      <div className="mx-auto max-w-2xl space-y-6">
        <h1 className="text-xl font-semibold">Ingestão</h1>

        <label className="block rounded border border-dashed border-neutral-700 p-6 text-center hover:border-neutral-500">
          <span className="text-sm text-neutral-400">Selecionar arquivo de vídeo</span>
          <input
            type="file"
            accept="video/*"
            className="hidden"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) run(() => uploadVideo(file))
              e.target.value = ''
            }}
          />
        </label>

        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (url.trim()) run(() => downloadVideo(url.trim()))
          }}
        >
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
            className="flex-1 rounded bg-neutral-900 px-3 py-2 text-sm outline-none ring-1 ring-neutral-800 focus:ring-neutral-600"
          />
          <button
            disabled={busy || !url.trim()}
            className="rounded bg-neutral-100 px-4 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
          >
            Baixar
          </button>
        </form>

        {busy && <p className="text-sm text-neutral-400">Processando…</p>}
        {error && <p className="text-sm text-red-400">{error}</p>}

        <ul className="space-y-2">
          {items.map((it) => (
            <li key={it.video_id} className="rounded bg-neutral-900 p-3 font-mono text-xs">
              <div>{it.video_id} · {it.filename} · {(it.size_bytes / 1_048_576).toFixed(1)} MB</div>
              <div className="truncate text-neutral-500">{it.source}</div>
            </li>
          ))}
        </ul>
      </div>
    </main>
  )
}
