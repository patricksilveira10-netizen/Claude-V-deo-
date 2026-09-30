import { fmt } from '../lib/timeline'
import type { Clip } from '../types'
import { CropControl } from './CropControl'
import { EditableWord } from './EditableWord'

interface Props {
  clip: Clip
  active: boolean
  cropRange: [number, number] | null // null = vídeo já é 9:16 ou mais estreito
  onSeek: () => void
  onToggle: () => void
  onWordChange: (index: number, text: string) => void
  onCropChange: (x: number) => void
  onZoomToggle: () => void
}

export function TimelineBlock({ clip, active, cropRange, onSeek, onToggle, onWordChange, onCropChange, onZoomToggle }: Props) {
  const keep = clip.type === 'keep'
  const duration = clip.end_time - clip.start_time

  return (
    <li
      className={`rounded-lg border p-3 ${
        keep ? 'border-neutral-800 bg-neutral-900' : 'border-red-950 bg-neutral-900/50'
      } ${active ? 'ring-2 ring-emerald-500' : ''}`}
    >
      <div className="flex items-center gap-3">
        <button type="button" onClick={onSeek} className="flex flex-1 items-center gap-3 text-left" title="Ir para este trecho">
          <span className="font-mono text-xs text-neutral-500">#{clip.clip_id}</span>
          <span
            className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
              keep ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
            }`}
          >
            {clip.type}
          </span>
          <span className={`font-mono text-xs ${keep ? 'text-neutral-300' : 'text-neutral-500 line-through'}`}>
            {fmt(clip.start_time)} → {fmt(clip.end_time)}
          </span>
          <span className="font-mono text-xs text-neutral-600">{fmt(duration)}s</span>
          {!keep && <span className="text-xs text-neutral-600">{clip.reason}</span>}
        </button>
        {keep && (
          <button
            type="button"
            onClick={onZoomToggle}
            title="Zoom-in leve (1.0x → 1.1x) ao longo do bloco"
            className={`rounded-md px-3 py-1 text-xs font-semibold ${
              clip.zoom_in ? 'bg-sky-500 text-neutral-950 hover:bg-sky-400' : 'bg-neutral-800 text-neutral-400 hover:bg-neutral-700'
            }`}
          >
            🔍 Zoom
          </button>
        )}
        <button
          type="button"
          onClick={onToggle}
          className={`rounded-md px-3 py-1 text-xs font-semibold ${
            keep ? 'bg-neutral-800 text-red-400 hover:bg-red-500/20' : 'bg-neutral-800 text-emerald-400 hover:bg-emerald-500/20'
          }`}
        >
          {keep ? '✂ Cortar' : '↺ Manter'}
        </button>
      </div>

      {keep && (
        <div className="mt-3 space-y-3">
          <p className="flex flex-wrap gap-x-0.5 gap-y-1 leading-relaxed">
            {clip.transcript.length === 0 && <span className="text-sm italic text-neutral-600">(sem fala)</span>}
            {clip.transcript.map((w, i) => (
              <EditableWord
                // start garante unicidade; o texto remonta o componente se editado por fora
                key={`${w.start}-${w.word}`}
                word={w}
                onChange={(text) => onWordChange(i, text)}
              />
            ))}
          </p>
          {cropRange ? (
            <CropControl value={clip.crop_center_x} min={cropRange[0]} max={cropRange[1]} onChange={onCropChange} />
          ) : (
            <p className="text-xs text-neutral-600">Vídeo já é vertical — sem crop.</p>
          )}
        </div>
      )}
    </li>
  )
}
