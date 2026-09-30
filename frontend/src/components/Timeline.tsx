import { cropBounds, cropWidth, fmt, summary } from '../lib/timeline'
import type { VideoData } from '../types'
import { TimelineBlock } from './TimelineBlock'

interface Props {
  data: VideoData
  activeClipId: number | null
  dirty: boolean
  onSeek: (t: number) => void
  onToggle: (index: number) => void
  onWordChange: (index: number, wordIndex: number, text: string) => void
  onCropChange: (index: number, x: number) => void
  onZoomToggle: (index: number) => void
  onReset: () => void
}

export function Timeline({ data, activeClipId, dirty, onSeek, onToggle, onWordChange, onCropChange, onZoomToggle, onReset }: Props) {
  const { total, kept, keeps, cuts } = summary(data.timeline)
  const cropRange = cropWidth(data.metadata) < data.metadata.width ? cropBounds(data.metadata) : null
  const saved = total > 0 ? Math.round((1 - kept / total) * 100) : 0

  return (
    <div className="space-y-3">
      <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-neutral-800 bg-neutral-950 pb-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-400">Timeline</h2>
          <p className="font-mono text-xs text-neutral-500">
            {keeps} keep · {cuts} cut · final <span className="text-emerald-400">{fmt(kept)}s</span> de {fmt(total)}s
            {saved > 0 && <span className="text-neutral-600"> (−{saved}%)</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-neutral-500">
          <span>
            {data.metadata.width}×{data.metadata.height} · {data.metadata.fps}fps
          </span>
          <button
            type="button"
            onClick={onReset}
            disabled={!dirty}
            className="rounded-md bg-neutral-800 px-2 py-1 text-neutral-300 hover:bg-neutral-700 disabled:opacity-30"
          >
            Desfazer edições
          </button>
        </div>
      </div>

      <ol className="space-y-2">
        {data.timeline.map((clip, i) => (
          <TimelineBlock
            key={clip.clip_id}
            clip={clip}
            active={clip.clip_id === activeClipId}
            cropRange={cropRange}
            onSeek={() => onSeek(clip.start_time)}
            onToggle={() => onToggle(i)}
            onWordChange={(w, text) => onWordChange(i, w, text)}
            onCropChange={(x) => onCropChange(i, x)}
            onZoomToggle={() => onZoomToggle(i)}
          />
        ))}
      </ol>
    </div>
  )
}
