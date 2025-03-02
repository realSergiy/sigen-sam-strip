# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass
from typing import Iterable, List, Optional

from app_conf import API_URL
from dataclasses_json import dataclass_json


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


@dataclass
class RLEMask:
    """Core type for RLE mask."""
    size: List[int]
    counts: str
    order: str


@dataclass
class RLEMaskForObject:
    """Type for RLE mask associated with a specific object id."""
    object_id: int
    rle_mask: RLEMask


@dataclass
class RLEMaskListOnFrame:
    """Type for a list of object-associated RLE masks on a specific video frame."""
    frame_index: int
    rle_mask_list: List[RLEMaskForObject]
