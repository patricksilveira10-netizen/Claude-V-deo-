import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { clipAt, cropWidth } from '../lib/timeline'
import type { Clip, VideoData } from '../types'

interface Props {
  src: string
  data: VideoData | null
  activeClip: Clip | undefined
  skipCuts: boolean
  videoRef: RefObject<HTMLVideoElement | null>
  onActiveChange: (clipId: number | null) => void
}

export function VideoPreview({ src, data, activeClip, skipCuts, videoRef, onActiveChange }: Props) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  // Loop por frame só enquanto toca: detecta o bloco ativo e pula "cuts" com precisão
  // (timeupdate dispara só ~4x/s e deixaria vazar até 250ms do trecho cortado).
  const latest = useRef({ data, skipCuts, onActiveChange, lastId: null as number | null })
  useLayoutEffect(() => {
    latest.current = { ...latest.current, data, skipCuts, onActiveChange }
  })

  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    let raf = 0

    const tick = () => {
      const { data, skipCuts, onActiveChange, lastId } = latest.current
      if (data) {
        let clip = clipAt(data.timeline, video.currentTime)
        if (skipCuts && !video.paused && clip?.type === 'cut') {
          video.currentTime = clip.end_time + 0.001
          clip = clipAt(data.timeline, video.currentTime)
        }
        const id = clip?.clip_id ?? null
        if (id !== lastId) {
          latest.current.lastId = id
          onActiveChange(id)
        }
      }
      if (!video.paused) raf = requestAnimationFrame(tick)
    }
    const start = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(tick)
    }

    video.addEventListener('play', start)
    video.addEventListener('seeked', tick)
    return () => {
      cancelAnimationFrame(raf)
      video.removeEventListener('play', start)
      video.removeEventListener('seeked', tick)
    }
  }, [videoRef, src])

  const meta = data?.metadata
  const cropW = meta ? cropWidth(meta) : 0
  const showCrop = meta && activeClip?.type === 'keep' && cropW < meta.width
  const left = showCrop ? ((activeClip.crop_center_x - cropW / 2) / meta.width) * 100 : 0
  const width = showCrop ? (cropW / meta.width) * 100 : 0

  return (
    <div
      className="relative mx-auto w-full max-h-[60vh] overflow-hidden rounded-lg bg-black"
      style={{ aspectRatio: meta ? `${meta.width} / ${meta.height}` : '16 / 9' }}
    >
      <video
        ref={videoRef}
        src={src}
        controls
        preload="metadata"
        onError={() => setFailedSrc(src)}
        className="absolute inset-0 h-full w-full"
      />
      {failedSrc === src && (
        <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-amber-300">
          O navegador não reproduz o codec deste arquivo (ex.: HEVC/AV1). A timeline e a renderização funcionam normalmente.
        </div>
      )}
      {showCrop && (
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute inset-y-0 left-0 bg-black/60" style={{ width: `${left}%` }} />
          <div className="absolute inset-y-0 right-0 bg-black/60" style={{ width: `${100 - left - width}%` }} />
          <div className="absolute inset-y-0 border-2 border-emerald-400" style={{ left: `${left}%`, width: `${width}%` }} />
        </div>
      )}
      {activeClip?.type === 'cut' && (
        <div className="pointer-events-none absolute left-2 top-2 rounded bg-red-600 px-2 py-0.5 text-xs font-bold">
          CORTE
        </div>
      )}
    </div>
  )
}
