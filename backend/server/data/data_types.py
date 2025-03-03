from dataclasses import dataclass
from typing import Iterable, List, Optional

from app_conf import API_URL
from data.resolver import resolve_videos
from dataclasses_json import dataclass_json, LetterCase

@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class Video:
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

@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class RLEMask:
    """Core type for RLE mask."""

    size: List[int]
    counts: str
    order: str

@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class RLEMaskForObject:
    """Type for RLE mask associated with a specific object id."""

    object_id: int
    rle_mask: RLEMask

@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class RLEMaskListOnFrame:
    """Type for a list of object-associated RLE masks on a specific video frame."""

    frame_index: int
    rle_mask_list: List[RLEMaskForObject]


# input
class StartSessionInput:
    path: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class StartSession:
    session_id: str


# input
class PingInput:
    session_id: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class Pong:
    success: bool


# input
class CloseSessionInput:
    session_id: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class CloseSession:
    success: bool


# input
class AddPointsInput:
    session_id: str
    frame_index: int
    clear_old_points: bool
    object_id: int
    labels: List[int]
    points: List[List[float]]


# input
class ClearPointsInFrameInput:
    session_id: str
    frame_index: int
    object_id: int


# input
class ClearPointsInVideoInput:
    session_id: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class ClearPointsInVideo:
    success: bool


# input
class RemoveObjectInput:
    session_id: str
    object_id: int


# input
class PropagateInVideoInput:
    session_id: str
    start_frame_index: int


# input
class CancelPropagateInVideoInput:
    session_id: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class CancelPropagateInVideo:
    success: bool


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass
class SessionExpiration:
    session_id: str
    expiration_time: int
    max_expiration_time: int
    ttl: int
