from dataclasses import dataclass
from typing import Iterable, List, Optional

from app_conf import API_URL
from data.resolver import resolve_videos
from flask_openapi3 import FileStorage

from pydantic import BaseModel

class Video(BaseModel):
    """Core type for video."""

    code: str
    path: str
    poster_path: Optional[str]
    width: int
    height: int

    def url(self) -> str:
        return f"{API_URL}/{self.path}"

    def poster_url(self) -> str:
        return f"{API_URL}/{self.poster_path}"

class VideoResponse(BaseModel):
    """Standard video response format"""
    id: str
    height: int
    width: int
    url: str
    path: str
    posterPath: Optional[str] = None
    posterUrl: Optional[str] = None

class UploadVideoInput(BaseModel):
    """Request model for video upload endpoint"""
    file: FileStorage
    start_time_sec: Optional[float] = None
    duration_time_sec: Optional[float] = None

class RLEMask(BaseModel):
    """Core type for RLE mask."""

    size: List[int]
    counts: str
    order: str

class RLEMaskForObject(BaseModel):
    """Type for RLE mask associated with a specific object id."""

    object_id: int
    rle_mask: RLEMask

class RLEMaskListOnFrame(BaseModel):
    """Type for a list of object-associated RLE masks on a specific video frame."""

    frame_index: int
    rle_mask_list: List[RLEMaskForObject]

class StartSessionInput(BaseModel):
    path: str

class StartSession(BaseModel):
    session_id: str

class PingInput(BaseModel):
    session_id: str

class Pong(BaseModel):
    success: bool

class CloseSessionInput(BaseModel):
    session_id: str

class CloseSession(BaseModel):
    success: bool

class AddPointsInput(BaseModel):
    session_id: str
    frame_index: int
    clear_old_points: bool
    object_id: int
    labels: List[int]
    points: List[List[float]]

class ClearPointsInFrameInput(BaseModel):
    session_id: str
    frame_index: int
    object_id: int

class ClearPointsInVideoInput(BaseModel):
    session_id: str

class ClearPointsInVideo(BaseModel):
    success: bool

class RemoveObjectInput(BaseModel):
    session_id: str
    object_id: int

class PropagateInVideoInput(BaseModel):
    session_id: str
    start_frame_index: int

class CancelPropagateInVideoInput(BaseModel):
    session_id: str

class CancelPropagateInVideo(BaseModel):
    success: bool

class SessionExpiration(BaseModel):
    session_id: str
    expiration_time: int
    max_expiration_time: int
    ttl: int
