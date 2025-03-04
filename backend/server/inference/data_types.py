# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from torch import Tensor


@dataclass
class Mask:
    size: List[int]
    counts: str


@dataclass
class BaseRequest:
    type: str


@dataclass
class StartSessionRequest(BaseRequest):
    type: str
    path: str
    session_id: Optional[str] = None


@dataclass
class SaveSessionRequest(BaseRequest):
    type: str
    session_id: str


@dataclass
class LoadSessionRequest(BaseRequest):
    type: str
    session_id: str


@dataclass
class RenewSessionRequest(BaseRequest):
    type: str
    session_id: str


@dataclass
class CloseSessionRequest(BaseRequest):
    type: str
    session_id: str


@dataclass
class AddPointsRequest(BaseRequest):
    type: str
    session_id: str
    frame_index: int
    clear_old_points: bool
    object_id: int
    labels: List[int]
    points: List[List[float]]


@dataclass
class AddMaskRequest(BaseRequest):
    type: str
    session_id: str
    frame_index: int
    object_id: int
    mask: Mask


@dataclass
class ClearPointsInFrameRequest(BaseRequest):
    type: str
    session_id: str
    frame_index: int
    object_id: int


@dataclass
class ClearPointsInVideoRequest(BaseRequest):
    type: str
    session_id: str


@dataclass
class RemoveObjectRequest(BaseRequest):
    type: str
    session_id: str
    object_id: int


@dataclass
class PropagateInVideoRequest(BaseRequest):
    type: str
    session_id: str
    start_frame_index: int


@dataclass
class CancelPropagateInVideoRequest(BaseRequest):
    type: str
    session_id: str


@dataclass
class StartSessionResponse:
    session_id: str


@dataclass
class SaveSessionResponse:
    session_id: str


@dataclass
class LoadSessionResponse:
    session_id: str


@dataclass
class RenewSessionResponse:
    session_id: str


@dataclass
class CloseSessionResponse:
    success: bool


@dataclass
class ClearPointsInVideoResponse:
    success: bool


@dataclass
class PropagateDataValue:
    object_id: int
    mask: Mask


@dataclass
class PropagateDataResponse:
    frame_index: int
    results: List[PropagateDataValue]


@dataclass
class RemoveObjectResponse:
    results: List[PropagateDataResponse]


@dataclass
class CancelPorpagateResponse:
    success: bool


@dataclass
class InferenceSession:
    start_time: float
    last_use_time: float
    session_id: str
    state: Dict[str, Dict[str, Union[Tensor, Dict[int, Tensor]]]]
