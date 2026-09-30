import type { Clip, VideoData, VideoMetadata } from '../types'

/** Largura do crop 9:16 — mesma regra de processor.py (_crop_centers). */
export function cropWidth({ width, height }: VideoMetadata): number {
  return Math.min(width, Math.floor(Math.round((height * 9) / 16) / 2) * 2)
}

export function cropBounds(meta: VideoMetadata): [number, number] {
  const half = cropWidth(meta) / 2
  return [Math.round(half), Math.round(meta.width - half)]
}

export const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi)

export const fmt = (t: number) => t.toFixed(2)

export function clipAt(timeline: Clip[], t: number): Clip | undefined {
  return timeline.find((c) => t >= c.start_time && t < c.end_time)
}

/** Crop do bloco "keep" mais próximo — usado quando um "cut" vira "keep" pela primeira vez. */
export function nearestCrop(data: VideoData, index: number): number {
  const tl = data.timeline
  for (let d = 1; d < tl.length; d++) {
    for (const i of [index - d, index + d]) {
      const c = tl[i]
      if (c?.type === 'keep') return c.crop_center_x
    }
  }
  return Math.round(data.metadata.width / 2)
}

export function summary(timeline: Clip[]) {
  const total = timeline.length ? timeline[timeline.length - 1].end_time : 0
  const kept = timeline.reduce((acc, c) => acc + (c.type === 'keep' ? c.end_time - c.start_time : 0), 0)
  return { total, kept, keeps: timeline.filter((c) => c.type === 'keep').length, cuts: timeline.filter((c) => c.type === 'cut').length }
}
