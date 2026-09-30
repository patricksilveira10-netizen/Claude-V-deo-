from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Word(_Strict):
    word: str
    start: float
    end: float


class VideoMetadata(_Strict):
    width: int
    height: int
    fps: float


class KeepClip(_Strict):
    clip_id: int
    type: Literal["keep"] = "keep"
    start_time: float
    end_time: float
    crop_center_x: int
    transcript: list[Word]
    zoom_in: bool = False


class CutClip(_Strict):
    clip_id: int
    type: Literal["cut"] = "cut"
    start_time: float
    end_time: float
    reason: str = "silence"


Clip = Annotated[Union[KeepClip, CutClip], Field(discriminator="type")]


class VideoData(_Strict):
    video_path: str
    metadata: VideoMetadata
    timeline: list[Clip]
