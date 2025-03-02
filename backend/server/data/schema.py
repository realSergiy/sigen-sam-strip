# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from typing import Iterable

import strawberry
from app_conf import (
    DEFAULT_VIDEO_PATH,
)
from data.data_types import (
    Video,
)
from data.store import get_videos
from strawberry import relay


@strawberry.type
class Query:

    @strawberry.field
    def default_video(self) -> Video:
        """
        Return the default video.

        The default video can be set with the DEFAULT_VIDEO_PATH environment
        variable. It will return the video that matches this path. If no video
        is found, it will return the first video.
        """
        all_videos = get_videos()

        # Find the video that matches the default path and return that as
        # default video.
        for _, v in all_videos.items():
            if v.path == DEFAULT_VIDEO_PATH:
                return v

        # Fallback is returning the first video
        return next(iter(all_videos.values()))

    @relay.connection(relay.ListConnection[Video])
    def videos(
        self,
    ) -> Iterable[Video]:
        """
        Return all available videos.
        """
        all_videos = get_videos()
        return all_videos.values()


schema = strawberry.Schema(
    query=Query,    
)
