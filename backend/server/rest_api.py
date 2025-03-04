# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import hashlib
import os
import shutil
import tempfile
from typing import Optional, Tuple, Union

import av
from app_conf import (
    DATA_PATH,
    DEFAULT_VIDEO_PATH,
    MAX_UPLOAD_VIDEO_DURATION,
    UPLOADS_PATH,
    UPLOADS_PREFIX,
)
from data.data_types import (
    AddPointsInput,
    CancelPropagateInVideo,
    CancelPropagateInVideoInput,
    ClearPointsInFrameInput,
    ClearPointsInVideo,
    ClearPointsInVideoInput,
    CloseSession,
    CloseSessionInput,
    RemoveObjectInput,
    RLEMask,
    RLEMaskForObject,
    RLEMaskListOnFrame,
    StartSession,
    StartSessionInput,
    UploadVideoInput,
    VideoResponse,
)
from data.loader import get_video
from data.store import get_videos
from data.transcoder import get_video_metadata, transcode, VideoMetadata
from inference.data_types import (
    AddPointsRequest,
    CancelPropagateInVideoRequest,
    ClearPointsInFrameRequest,
    ClearPointsInVideoRequest,
    CloseSessionRequest,
    RemoveObjectRequest,
    StartSessionRequest,
)
from inference.predictor import InferenceAPI
import logging
from flask import Blueprint, request

# Ensure all loggers are at INFO level
logging.getLogger('inference').setLevel(logging.INFO)
from werkzeug.datastructures import FileStorage

from flask_pydantic import validate


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

rest_api = Blueprint('rest_api', __name__)

def create_rest_api(inference_api: InferenceAPI):
    """Create REST API routes with the given inference API instance."""

    @rest_api.route("/api/default_video", methods=["GET"])
    def default_video():
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
                return {
                    "id": v.code,
                    "height": v.height,
                    "width": v.width,
                    "url": v.url(),
                    "path": v.path,
                    "posterPath": v.poster_path,
                    "posterUrl": v.poster_url() if v.poster_path else None
                }

        # Fallback is returning the first video
        first_video = next(iter(all_videos.values()))
        return {
            "id": first_video.code,
            "height": first_video.height,
            "width": first_video.width,
            "url": first_video.url(),
            "path": first_video.path,
            "posterPath": first_video.poster_path,
            "posterUrl": first_video.poster_url() if first_video.poster_path else None
        }

    @rest_api.route("/api/videos", methods=["GET"])
    @validate()
    def videos():
        """
        Return all available videos.
        """
        all_videos = get_videos()
        return [
            VideoResponse(
                id=v.code,
                height=v.height,
                width=v.width,
                url=v.url(),
                path=v.path,
                posterPath=v.poster_path,
                posterUrl=v.poster_url() if v.poster_path else None
            )
            for v in all_videos.values()
        ]
    
    @rest_api.route("/api/upload_video", methods=["POST"])
    @validate()
    def upload_video(body: UploadVideoInput):
        filepath, file_key, vm = process_video(
            body.file,
            max_time=MAX_UPLOAD_VIDEO_DURATION,
            start_time_sec=body.startTimeSec,
            duration_time_sec=body.durationTimeSec,
        )

        video = get_video(
            filepath,
            UPLOADS_PATH,
            file_key=file_key,
            width=vm.width,
            height=vm.height,
            generate_poster=False,
        )
        return VideoResponse(
            id=video.code,
            height=video.height,
            width=video.width,
            url=video.url(),
            path=video.path,
            posterPath=video.poster_path,
            posterUrl=video.poster_url() if video.poster_path else None
        )

    @rest_api.route("/api/start_session", methods=["POST"])
    @validate()
    def start_session(body: StartSessionInput):        
        path = body.path
        
        if not path:
            return {"error": "Path is required"}, 400
            
        request_obj = StartSessionRequest(
            type="start_session",
            path=f"{DATA_PATH}/{path}",
        )
        
        res = inference_api.start_session(request=request_obj)
        return StartSession(sessionId=res.session_id)
            
    @rest_api.route("/api/close_session", methods=["POST"])
    @validate()
    def close_session(body: CloseSessionInput):
        session_id = body.sessionId
        
        request_obj = CloseSessionRequest(
            type="close_session",
            session_id=session_id,
        )
        
        response = inference_api.close_session(request=request_obj)
        
        return CloseSession(success=response.success)

    @rest_api.route("/api/add_points", methods=["POST"])
    @validate()
    def add_points(body: AddPointsInput):
        logger.info(f'add_points: {body}')
        
        request_obj = AddPointsRequest(
            type="add_points",
            session_id=body.sessionId,
            frame_index=body.frameIndex,
            object_id=body.objectId,
            points=body.points,
            labels=body.labels,
            clear_old_points=body.clearOldPoints,
        )
        
        response = inference_api.add_points(request=request_obj)
        
        return RLEMaskListOnFrame(
            frameIndex=response.frame_index,
            rleMaskList=[
                RLEMaskForObject(
                    objectId=r.object_id,
                    rleMask=RLEMask(counts=r.mask.counts, size=r.mask.size, order="F"),
                )
                for r in response.results
            ],
        )

    @rest_api.route("/api/remove_object", methods=["POST"])
    @validate()
    def remove_object(body: RemoveObjectInput):
        request_obj = RemoveObjectRequest(
            type="remove_object",
            session_id=body.sessionId,
            object_id=body.objectId,
        )
        
        response = inference_api.remove_object(request=request_obj)

        return [
            RLEMaskListOnFrame(
                frameIndex=res.frame_index,
                rleMaskList=[
                    RLEMaskForObject(
                        objectId=r.object_id,
                        rleMask=RLEMask(
                            counts=r.mask.counts, size=r.mask.size, order="F"
                        ),
                    )
                    for r in res.results
                ],
            )
            for res in response.results
        ]

    @rest_api.route("/api/clear_points_in_frame", methods=["POST"])
    @validate()
    def clear_points_in_frame(body: ClearPointsInFrameInput):
        request_obj = ClearPointsInFrameRequest(
            type="clear_points_in_frame",
            session_id=body.sessionId,
            frame_index=body.frameIndex,
            object_id=body.objectId,
        )

        response = inference_api.clear_points_in_frame(request=request_obj)

        return RLEMaskListOnFrame(
            frameIndex=response.frame_index,
            rleMaskList=[
                RLEMaskForObject(
                    objectId=r.object_id,
                    rleMask=RLEMask(counts=r.mask.counts, size=r.mask.size, order="F"),
                )
                for r in response.results
            ],
        )

    @rest_api.route("/api/clear_points_in_video", methods=["POST"])
    @validate()
    def clear_points_in_video(body: ClearPointsInVideoInput):
        request_obj = ClearPointsInVideoRequest(
            type="clear_points_in_video",
            session_id=body.sessionId,
        )
        
        response = inference_api.clear_points_in_video(request=request_obj)
        
        return ClearPointsInVideo(success=response.success)

    @rest_api.route("/api/cancel_propagate_in_video", methods=["POST"])
    @validate()
    def cancel_propagate_in_video(body: CancelPropagateInVideoInput):
        request_obj = CancelPropagateInVideoRequest(
            type="cancel_propagate_in_video",
            session_id=body.sessionId,
        )
        
        response = inference_api.cancel_propagate_in_video(request=request_obj)
        
        return CancelPropagateInVideo(success=response.success)

    return rest_api

def get_file_hash(video_path_or_file) -> str:
    if isinstance(video_path_or_file, str):
        with open(video_path_or_file, "rb") as in_f:
            result = hashlib.sha256(in_f.read()).hexdigest()
    else:
        video_path_or_file.seek(0)
        result = hashlib.sha256(video_path_or_file.read()).hexdigest()
    return result


def _get_start_sec_duration_sec(
    start_time_sec: Union[float, None],
    duration_time_sec: Union[float, None],
    max_time: float,
) -> Tuple[float, float]:
    default_seek_t = int(os.environ.get("VIDEO_ENCODE_SEEK_TIME", "0"))
    if start_time_sec is None:
        start_time_sec = default_seek_t

    if duration_time_sec is not None:
        duration_time_sec = min(duration_time_sec, max_time)
    else:
        duration_time_sec = max_time
    return start_time_sec, duration_time_sec


def process_video(
    file: FileStorage,
    max_time: float,
    start_time_sec: Optional[float] = None,
    duration_time_sec: Optional[float] = None,
) -> Tuple[Optional[str], str, str, VideoMetadata]:
    """
    Process file upload including video trimming and content moderation checks.

    Returns the filepath, s3_file_key, hash & video metadata as a tuple.
    """
    with tempfile.TemporaryDirectory() as tempdir:
        in_path = f"{tempdir}/in.mp4"
        out_path = f"{tempdir}/out.mp4"
        file.save(in_path)

        try:
            video_metadata = get_video_metadata(in_path)
        except av.InvalidDataError:
            raise Exception("not valid video file")

        if video_metadata.num_video_streams == 0:
            raise Exception("video container does not contain a video stream")
        if video_metadata.width is None or video_metadata.height is None:
            raise Exception("video container does not contain width or height metadata")

        if video_metadata.duration_sec in (None, 0):
            raise Exception("video container does time duration metadata")

        start_time_sec, duration_time_sec = _get_start_sec_duration_sec(
            max_time=max_time,
            start_time_sec=start_time_sec,
            duration_time_sec=duration_time_sec,
        )

        # Transcode video to make sure videos returned to the app are all in
        # the same format, duration, resolution, fps.
        transcode(
            in_path,
            out_path,
            video_metadata,
            seek_t=start_time_sec,
            duration_time_sec=duration_time_sec,
        )

        os.remove(in_path)  # don't need original video now

        out_video_metadata = get_video_metadata(out_path)
        if out_video_metadata.num_video_frames == 0:
            raise Exception(
                "transcode produced empty video; check seek time or your input video"
            )

        filepath = None
        file_key = None
        with open(out_path, "rb") as file_data:
            file_hash = get_file_hash(file_data)
            file_data.seek(0)

            file_key = UPLOADS_PREFIX + "/" + f"{file_hash}.mp4"
            filepath = os.path.join(UPLOADS_PATH, f"{file_hash}.mp4")

        assert filepath is not None and file_key is not None
        shutil.move(out_path, filepath)

        return filepath, file_key, out_video_metadata
