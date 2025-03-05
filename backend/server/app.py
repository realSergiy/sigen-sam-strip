# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import logging
import sys
from typing import Generator

from app_conf import (
    DATA_PATH,
)
from api_utils import create_rle_mask_list_on_frame
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
    StartSession,
    StartSessionInput,
)
from data.loader import preload_data
from data.store import set_videos
from flask import jsonify, make_response, Response
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
    
    # Check if the path is a URL (starts with http:// or https://)
    if path.startswith("http://") or path.startswith("https://"):
        # For URLs, pass the URL directly to the predictor
        video_path = path
    else:
        # For local paths, prepend the DATA_PATH
        video_path = f"{DATA_PATH}/{path}"
        
    request_obj = StartSessionRequest(
        type="start_session",
        path=video_path,
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
    
    return create_rle_mask_list_on_frame(response)


@app.post("/api/remove_object", summary="remove an object", tags=[Tag(name="segmentation", description="video segmentation operations")])
@validate()
def remove_object(body: RemoveObjectInput):
    request_obj = RemoveObjectRequest(
        type="remove_object",
        session_id=body.sessionId,
        object_id=body.objectId,
    )
    
    response = inference_api.remove_object(request=request_obj)

    return [create_rle_mask_list_on_frame(res) for res in response.results]


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

    return create_rle_mask_list_on_frame(response)


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
@app.post("/api/propagate_in_video", summary="propagate mask in video", tags=[Tag(name="segmentation", description="video segmentation operations")])
def propagate_in_video(body: PropagateInVideoInput) -> Response:    
    session_id = body.sessionId
    start_frame_index = body.startFrameIndex
    boundary = "frame"
    
    def generate():
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
    
    return Response(generate(), mimetype="multipart/x-savi-stream; boundary=" + boundary)


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
