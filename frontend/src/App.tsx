import { useRef, useState } from 'react'
import { IngestForm } from './components/IngestForm'
import { Timeline } from './components/Timeline'
import { VideoPreview } from './components/VideoPreview'
import { downloadVideo, mediaUrl, processVideo, renderVideo, uploadVideo } from './lib/api'
import { nearestCrop } from './lib/timeline'
import type { Clip, IngestResult, VideoData } from './types'

type Stage = 'idle' | 'ingesting' | 'processing' | 'ready' | 'rendering'

const STAGE_LABEL: Record<Stage, string> = {
  idle: '',
  ingesting: 'Recebendo vídeo…',
  processing: 'Analisando (áudio → Whisper → cortes → face tracking)…',
  ready: '',
  rendering: 'Renderizando…',
}

export default function App() {
  const [stage, setStage] = useState<Stage>('idle')
  const [error, setError] = useState<string | null>(null)
  const [language, setLanguage] = useState('')
  const [videoId, setVideoId] = useState<string | null>(null)
  const [original, setOriginal] = useState<VideoData | null>(null)
  const [data, setData] = useState<VideoData | null>(null)
  const [activeClipId, setActiveClipId] = useState<number | null>(null)
  const [skipCuts, setSkipCuts] = useState(true)
  const [renderResult, setRenderResult] = useState<unknown>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  // Última versão de cada bloco no tipo oposto: alternar keep→cut→keep não perde transcrição nem crop.
  const stash = useRef(new Map<number, Clip>())

  const busy = stage === 'ingesting' || stage === 'processing' || stage === 'rendering'

  async function analyze(id: string) {
    setStage('processing')
    setError(null)
    try {
      const result = await processVideo(id, language || null)
      stash.current.clear()
      setOriginal(result)
      setData(result)
      setStage('ready')
    } catch (e) {
      setError(`Análise falhou: ${(e as Error).message}`)
      setStage('idle')
    }
  }

  async function ingest(task: () => Promise<IngestResult>) {
    setStage('ingesting')
    setError(null)
    setRenderResult(null)
    try {
      const { video_id } = await task()
      setVideoId(video_id)
      setOriginal(null)
      setData(null)
      setActiveClipId(null)
      await analyze(video_id)
    } catch (e) {
      setError(`Ingestão falhou: ${(e as Error).message}`)
      setStage('idle')
    }
  }

  function updateClip(index: number, fn: (c: Clip) => Clip) {
    setData((d) => d && { ...d, timeline: d.timeline.map((c, i) => (i === index ? fn(c) : c)) })
  }

  function toggleClip(index: number) {
    if (!data) return
    const clip = data.timeline[index]
    const restored = stash.current.get(clip.clip_id)
    stash.current.set(clip.clip_id, clip)
    const { clip_id, start_time, end_time } = clip
    const next: Clip =
      restored ??
      (clip.type === 'keep'
        ? { clip_id, type: 'cut', start_time, end_time, reason: 'manual' }
        : { clip_id, type: 'keep', start_time, end_time, crop_center_x: nearestCrop(data, index), transcript: [] })
    updateClip(index, () => next)
  }

  function editWord(index: number, wordIndex: number, text: string) {
    updateClip(index, (c) =>
      c.type === 'keep' ? { ...c, transcript: c.transcript.map((w, i) => (i === wordIndex ? { ...w, word: text } : w)) } : c,
    )
  }

  function setCrop(index: number, x: number) {
    updateClip(index, (c) => (c.type === 'keep' ? { ...c, crop_center_x: x } : c))
  }

  function seek(t: number) {
    const v = videoRef.current
    if (v) v.currentTime = t + 0.001
  }

  async function render() {
    if (!data) return
    setStage('rendering')
    setError(null)
    setRenderResult(null)
    try {
      setRenderResult(await renderVideo(data))
    } catch (e) {
      setError(`Renderização falhou: ${(e as Error).message}`)
    } finally {
      setStage('ready')
    }
  }

  const activeClip = data?.timeline.find((c) => c.clip_id === activeClipId)
  const canRender = !!data && !busy && data.timeline.some((c) => c.type === 'keep')

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 lg:grid lg:h-screen lg:grid-cols-2">
      {/* ── Coluna esquerda: inputs + preview ── */}
      <section className="flex flex-col gap-4 border-neutral-800 p-5 lg:overflow-y-auto lg:border-r">
        <h1 className="text-lg font-bold tracking-tight">
          Shorts Engine <span className="font-normal text-neutral-500">· ajuste</span>
        </h1>

        <IngestForm
          disabled={busy}
          language={language}
          onLanguageChange={setLanguage}
          onUrl={(url) => ingest(() => downloadVideo(url))}
          onFile={(file) => ingest(() => uploadVideo(file))}
        />

        {busy && (
          <div className="rounded-md bg-neutral-900 px-3 py-2 text-sm text-amber-300">{STAGE_LABEL[stage]}</div>
        )}
        {error && (
          <div className="flex items-center justify-between gap-3 rounded-md bg-red-950/60 px-3 py-2 text-sm text-red-300">
            <span className="break-words">{error}</span>
            {videoId && !data && !busy && (
              <button onClick={() => analyze(videoId)} className="shrink-0 rounded bg-red-900 px-2 py-1 text-xs hover:bg-red-800">
                Reprocessar
              </button>
            )}
          </div>
        )}

        {videoId ? (
          <>
            <VideoPreview
              src={mediaUrl(videoId)}
              data={data}
              activeClip={activeClip}
              skipCuts={skipCuts}
              videoRef={videoRef}
              onActiveChange={setActiveClipId}
            />
            <label className="flex items-center gap-2 text-sm text-neutral-400">
              <input type="checkbox" checked={skipCuts} onChange={(e) => setSkipCuts(e.target.checked)} className="accent-emerald-500" />
              Pular blocos "cut" no preview
              <span className="ml-auto font-mono text-xs text-neutral-600">{videoId}</span>
            </label>
          </>
        ) : (
          <div className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-neutral-800 text-sm text-neutral-600">
            Nenhum vídeo carregado
          </div>
        )}

        <button
          onClick={render}
          disabled={!canRender}
          className="mt-auto w-full rounded-xl bg-emerald-500 py-6 text-xl font-black tracking-wide text-neutral-950 shadow-lg shadow-emerald-500/20 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-600 disabled:shadow-none"
        >
          {stage === 'rendering' ? 'RENDERIZANDO…' : 'RENDERIZAR VÍDEO FINAL'}
        </button>
        {renderResult !== null && (
          <pre className="overflow-x-auto rounded-md bg-neutral-900 p-3 font-mono text-xs text-emerald-300">
            {JSON.stringify(renderResult, null, 2)}
          </pre>
        )}
      </section>

      {/* ── Coluna direita: timeline editável ── */}
      <section className="p-5 lg:overflow-y-auto">
        {data ? (
          <Timeline
            data={data}
            activeClipId={activeClipId}
            dirty={data !== original}
            onSeek={seek}
            onToggle={toggleClip}
            onWordChange={editWord}
            onCropChange={setCrop}
            onReset={() => {
              stash.current.clear()
              setData(original)
            }}
          />
        ) : (
          <div className="flex h-full min-h-40 items-center justify-center text-sm text-neutral-600">
            {stage === 'processing' ? 'Gerando timeline…' : 'A timeline aparece aqui após a análise.'}
          </div>
        )}
      </section>
    </div>
  )
}
