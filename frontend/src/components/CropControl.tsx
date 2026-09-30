import { clamp } from '../lib/timeline'

interface Props {
  value: number
  min: number
  max: number
  onChange: (v: number) => void
}

export function CropControl({ value, min, max, onChange }: Props) {
  const commit = (raw: string) => {
    const n = Number.parseInt(raw, 10)
    if (Number.isFinite(n)) onChange(clamp(n, min, max))
  }

  return (
    <div className="flex items-center gap-3">
      <span className="shrink-0 text-xs uppercase tracking-wide text-neutral-500">Crop X</span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="min-w-0 flex-1 accent-emerald-500"
      />
      {/* key={value}: remonta quando o slider muda; digitar só confirma no blur/Enter (sem clamp a cada tecla). */}
      <input
        key={value}
        type="number"
        min={min}
        max={max}
        defaultValue={value}
        onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && commit(e.currentTarget.value)}
        className="w-20 rounded bg-neutral-950 px-2 py-1 text-right font-mono text-xs outline-none ring-1 ring-neutral-700 focus:ring-emerald-500"
      />
    </div>
  )
}
