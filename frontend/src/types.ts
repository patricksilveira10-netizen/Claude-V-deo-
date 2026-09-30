// Espelho de backend/schemas.py — o backend rejeita campos extras.
export interface Word {
  word: string
  start: number
  end: number
}

export interface VideoMetadata {
  width: number
  height: number
  fps: number
}

export interface KeepClip {
  clip_id: number
  type: 'keep'
  start_time: number
  end_time: number
  crop_center_x: number
  transcript: Word[]
}

export interface CutClip {
  clip_id: number
  type: 'cut'
  start_time: number
  end_time: number
  reason: string
}

export type Clip = KeepClip | CutClip

export interface VideoData {
  video_path: string
  metadata: VideoMetadata
  timeline: Clip[]
}

export interface IngestResult {
  video_id: string
  filename: string
  path: string
  size_bytes: number
  source: string
}
