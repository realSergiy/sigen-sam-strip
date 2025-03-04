# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import hashlib
import logging
import os
import shutil
import sys
import tempfile
from typing import Generator, Optional, Tuple, Union

import av
from app_conf import (
    DATA_PATH,
    DEFAULT_VIDEO_PATH,
    GALLERY_PATH,
    GALLERY_PREFIX,
    MAX_UPLOAD_VIDEO_DURATION,
    POSTERS_PATH,
    POSTERS_PREFIX,
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
from data.loader import get_video, preload_data
from data.store import get_videos, set_videos
from data.transcoder import get_video_metadata, transcode, VideoMetadata
from flask import make_response, request, Response, send_from_directory
from flask_cors import CORS
from flask_pydantic import validate
from inference.data_types import (
    AddPointsRequest,
    CancelPropagateInVideoRequest,
    ClearPointsInFrameRequest,
    ClearPointsInVideoRequest,
    CloseSessionRequest,
    PropagateInVideoRequest,
    RemoveObjectRequest,
    StartSessionRequest,
)
from inference.multipart import MultipartResponseBuilder
from inference.predictor import InferenceAPI
from werkzeug.datastructures import FileStorage
from flask_openapi3 import Info, Tag, OpenAPI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)

logging.getLogger('inference').setLevel(logging.INFO)

logger = logging.getLogger(__name__)


info = Info(title="sigen-gallery-api", version="0.0.1")
app = OpenAPI(__name__, info=info)
cors = CORS(app, supports_credentials=True)

videos = preload_data()
set_videos(videos)

inference_api = InferenceAPI()


@app.get("/healthy", summary="health check", tags=[Tag(name="health", description="health check")])
def healthy():
    return make_response("OK", 200)


@app.get(f"/{GALLERY_PREFIX}/<path:path>", doc_ui=False)
def send_gallery_video(path: str):
    try:
        return send_from_directory(
            GALLERY_PATH,
            path,
        )
    except:
        raise ValueError("resource not found")


@app.get(f"/{POSTERS_PREFIX}/<path:path>", doc_ui=False)
def send_poster_image(path: str):
    try:
        return send_from_directory(
            POSTERS_PATH,
            path,
        )
    except:
        raise ValueError("resource not found")


@app.get(f"/{UPLOADS_PREFIX}/<path:path>", doc_ui=False)
def send_uploaded_video(path: str):
    try:
        return send_from_directory(
            UPLOADS_PATH,
            path,
        )
    except:
        raise ValueError("resource not found")


# TOOD: Protect route with ToS permission check
@app.post("/propagate_in_video", summary="propagate mask in video", tags=[Tag(name="segmentation", description="video segmentation operations")])
def propagate_in_video() -> Response:
    data = request.json
    args = {
        "session_id": data["session_id"],
        "start_frame_index": data.get("start_frame_index", 0),
    }

    boundary = "frame"
    frame = gen_track_with_mask_stream(boundary, **args)
    return Response(frame, mimetype="multipart/x-savi-stream; boundary=" + boundary)


def gen_track_with_mask_stream(
    boundary: str,
    session_id: str,
    start_frame_index: int,
) -> Generator[bytes, None, None]:
    with inference_api.autocast_context():
        request = PropagateInVideoRequest(
            type="propagate_in_video",
            session_id=session_id,
            start_frame_index=start_frame_index,
        )

        for chunk in inference_api.propagate_in_video(request=request):
            yield MultipartResponseBuilder.build(
                boundary=boundary,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Frame-Current": "-1",
                    # Total frames minus the reference frame
                    "Frame-Total": "-1",
                    "Mask-Type": "RLE[]",
                },
                body=chunk.to_json().encode("UTF-8"),
            ).get_message()


# Helper functions for video processing
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
) -> Tuple[Optional[str], str, VideoMetadata]:
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


# API Routes moved from rest_api.py
@app.get("/api/default_video", summary="get default video", tags=[Tag(name="videos", description="video management")])
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


@app.get("/api/videos", summary="list all videos", tags=[Tag(name="videos", description="video management")])
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


@app.post("/api/upload_video", summary="upload a new video", tags=[Tag(name="videos", description="video management")])
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


@app.post("/api/start_session", summary="start a new session", tags=[Tag(name="session", description="session management")])
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
        

@app.post("/api/close_session", summary="close an existing session", tags=[Tag(name="session", description="session management")])
@validate()
def close_session(body: CloseSessionInput):
    session_id = body.sessionId
    
    request_obj = CloseSessionRequest(
        type="close_session",
        session_id=session_id,
    )
    
    response = inference_api.close_session(request=request_obj)
    
    return CloseSession(success=response.success)


@app.post("/api/add_points", summary="add points to a frame", tags=[Tag(name="segmentation", description="video segmentation operations")])
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


@app.post("/api/remove_object", summary="remove an object", tags=[Tag(name="segmentation", description="video segmentation operations")])
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


@app.post("/api/clear_points_in_frame", summary="clear points in a frame", tags=[Tag(name="segmentation", description="video segmentation operations")])
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


@app.post("/api/clear_points_in_video", summary="clear all points in video", tags=[Tag(name="segmentation", description="video segmentation operations")])
@validate()
def clear_points_in_video(body: ClearPointsInVideoInput):
    request_obj = ClearPointsInVideoRequest(
        type="clear_points_in_video",
        session_id=body.sessionId,
    )
    
    response = inference_api.clear_points_in_video(request=request_obj)
    
    return ClearPointsInVideo(success=response.success)


@app.post("/api/cancel_propagate_in_video", summary="cancel mask propagation", tags=[Tag(name="segmentation", description="video segmentation operations")])
@validate()
def cancel_propagate_in_video(body: CancelPropagateInVideoInput):
    request_obj = CancelPropagateInVideoRequest(
        type="cancel_propagate_in_video",
        session_id=body.sessionId,
    )
    
    response = inference_api.cancel_propagate_in_video(request=request_obj)
    
    return CancelPropagateInVideo(success=response.success)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
