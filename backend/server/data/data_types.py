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
    startTimeSec: Optional[float] = None
    durationTimeSec: Optional[float] = None

class RLEMask(BaseModel):
    """Core type for RLE mask."""

    size: List[int]
    counts: str
    order: Optional[str] = None

class RLEMaskForObject(BaseModel):
    """Type for RLE mask associated with a specific object id."""

    objectId: int
    rleMask: RLEMask

class RLEMaskListOnFrame(BaseModel):
    """Type for a list of object-associated RLE masks on a specific video frame."""

    frameIndex: int
    rleMaskList: List[RLEMaskForObject]

class StartSessionInput(BaseModel):
    path: str

class StartSession(BaseModel):
    sessionId: str

class PingInput(BaseModel):
    sessionId: str

class Pong(BaseModel):
    success: bool

class CloseSessionInput(BaseModel):
    sessionId: str

class CloseSession(BaseModel):
    success: bool

class AddPointsInput(BaseModel):
    sessionId: str
    frameIndex: int
    clearOldPoints: bool
    objectId: int
    labels: List[int]
    points: List[List[float]]

class ClearPointsInFrameInput(BaseModel):
    sessionId: str
    frameIndex: int
    objectId: int

class ClearPointsInVideoInput(BaseModel):
    sessionId: str

class ClearPointsInVideo(BaseModel):
    success: bool

class RemoveObjectInput(BaseModel):
    sessionId: str
    objectId: int

class PropagateInVideoInput(BaseModel):
    sessionId: str
    startFrameIndex: int

class CancelPropagateInVideoInput(BaseModel):
    sessionId: str

class CancelPropagateInVideo(BaseModel):
    success: bool

class SessionExpiration(BaseModel):
    sessionId: str
    expirationTime: int
    maxExpirationTime: int
    ttl: int
