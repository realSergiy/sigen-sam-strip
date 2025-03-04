# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import logging
import sys
from typing import Generator

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
from api_utils import process_video
from inference.multipart import MultipartResponseBuilder
from data.data_types import (
    AddPointsInput,
    CancelPropagateInVideo,
    CancelPropagateInVideoInput,
    ClearPointsInFrameInput,
    ClearPointsInVideo,
    ClearPointsInVideoInput,
    CloseSession,
    CloseSessionInput,
    PropagateInVideoInput,
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
from inference.predictor import InferenceAPI
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

# TOOD: Protect route with ToS permission check
@app.post("/propagate_in_video", summary="propagate mask in video", tags=[Tag(name="segmentation", description="video segmentation operations")])
def propagate_in_video(body: PropagateInVideoInput) -> Response:    
    args = {
        "session_id": body.sessionId,        
        "start_frame_index": body.startFrameIndex
    }

    boundary = "frame"
    frame = gen_track_with_mask_stream(boundary, **args)
    return Response(frame, mimetype="multipart/x-savi-stream; boundary=" + boundary)


@app.post("/api/cancel_propagate_in_video", summary="cancel mask propagation", tags=[Tag(name="segmentation", description="video segmentation operations")])
@validate()
def cancel_propagate_in_video(body: CancelPropagateInVideoInput):
    request_obj = CancelPropagateInVideoRequest(
        type="cancel_propagate_in_video",
        session_id=body.sessionId,
    )
    
    response = inference_api.cancel_propagate_in_video(request=request_obj)
    
    return CancelPropagateInVideo(success=response.success)

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

# -- Gallery Routes (to remove) --

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
