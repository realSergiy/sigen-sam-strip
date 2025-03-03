# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import hashlib
import logging
import os
import tempfile
import shutil
from typing import Optional, Tuple, Union

from flask import Blueprint, jsonify, request
from inference.predictor import InferenceAPI
from data.loader import get_video
from data.transcoder import get_video_metadata, transcode, VideoMetadata
from app_conf import DATA_PATH, UPLOADS_PATH, UPLOADS_PREFIX, MAX_UPLOAD_VIDEO_DURATION, DEFAULT_VIDEO_PATH
from data.store import get_videos
from inference.data_types import (
    StartSessionRequest,
    CloseSessionRequest,
    AddPointsRequest,
    ClearPointsInFrameRequest,
    ClearPointsInVideoRequest,
    RemoveObjectRequest,
    CancelPropagateInVideoRequest,
)

from werkzeug.datastructures import FileStorage

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
    Video,
)

from data.schema import (
    dpr_default_video,
    dpr_videos,
    dpr_upload_video,
    inf_start_session,
    inf_close_session,
    inf_add_points,
    inf_remove_object,
    inf_clear_points_in_frame,
    inf_clear_points_in_video,
    inf_cancel_propagate_in_video
)

logger = logging.getLogger(__name__)

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
                return jsonify(v)

        # Fallback is returning the first video
        return jsonify(next(iter(all_videos.values())))
        

    @rest_api.route("/api/videos", methods=["GET"])
    def videos():
        """
        Return all available videos.
        """
        all_videos = get_videos().values()
        return jsonify(all_videos)

    @rest_api.route("/api/upload_video", methods=["POST"])
    def upload_video():
        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400
            
        # Get optional parameters
        start_time_sec = request.form.get('start_time_sec')
        duration_time_sec = request.form.get('duration_time_sec')
        
        # Convert to float if provided
        if start_time_sec is not None:
            start_time_sec = float(start_time_sec)
        if duration_time_sec is not None:
            duration_time_sec = float(duration_time_sec)

        max_time = MAX_UPLOAD_VIDEO_DURATION
        filepath, file_key, vm = process_video(
            file,
            max_time=max_time,
            start_time_sec=start_time_sec,
            duration_time_sec=duration_time_sec,
        )

        video = get_video(
            filepath,
            UPLOADS_PATH,
            file_key=file_key,
            width=vm.width,
            height=vm.height,
            generate_poster=False,
        )

        return jsonify(video)


    @rest_api.route("/api/start_session", methods=["POST"])
    def start_session():
        data = request.json
        path = data.get("path")
        
        if not path:
            return jsonify({"error": "Path is required"}), 400
            
        request_obj = StartSessionRequest(
            type="start_session",
            path=f"{DATA_PATH}/{path}",
        )
        
        response = inference_api.start_session(request=request_obj)
        
        return jsonify(StartSession(session_id=response.session_id))

    @rest_api.route("/api/close_session", methods=["POST"])
    def close_session():
        data = request.json
        session_id = data.get("session_id")
        
        if not session_id:
            return jsonify({"error": "Session ID is required"}), 400
            
        request_obj = CloseSessionRequest(
            type="close_session",
            session_id=session_id,
        )
        
        response = inference_api.close_session(request=request_obj)
        
        return jsonify({
            "success": response.success
        })

    @rest_api.route("/api/add_points", methods=["POST"])
    def add_points():
        data = request.json
        session_id = data.get("session_id")
        frame_index = data.get("frame_index")
        object_id = data.get("object_id")
        points = data.get("points")
        labels = data.get("labels")
        clear_old_points = data.get("clear_old_points", True)
        
        if not all([session_id, frame_index is not None, object_id is not None, points, labels]):
            return jsonify({"error": "Missing required parameters"}), 400
            
        request_obj = AddPointsRequest(
            type="add_points",
            session_id=session_id,
            frame_index=frame_index,
            object_id=object_id,
            points=points,
            labels=labels,
            clear_old_points=clear_old_points,
        )
        
        response = inference_api.add_points(request=request_obj)
        return jsonify(RLEMaskListOnFrame(
            frame_index=response.frame_index,
            rle_mask_list=[
                RLEMaskForObject(
                    object_id=r.object_id,
                    rle_mask=RLEMask(counts=r.mask.counts, size=r.mask.size, order="F"),
                )
                for r in response.results
            ],
        ))

    @rest_api.route("/api/remove_object", methods=["POST"])
    def remove_object():
        data = request.json
        session_id = data.get("session_id")
        object_id = data.get("object_id")
        
        if not all([session_id, object_id is not None]):
            return jsonify({"error": "Missing required parameters"}), 400
            
        request_obj = RemoveObjectRequest(
            type="remove_object",
            session_id=session_id,
            object_id=object_id,
        )
        
        response = inference_api.remove_object(request=request_obj)
        
        return jsonify([
            RLEMaskListOnFrame(
                frame_index=res.frame_index,
                rle_mask_list=[
                    RLEMaskForObject(
                        object_id=r.object_id,
                        rle_mask=RLEMask(
                            counts=r.mask.counts, size=r.mask.size, order="F"
                        ),
                    )
                    for r in res.results
                ],
            )
            for res in response.results
        ])

    @rest_api.route("/api/clear_points_in_frame", methods=["POST"])
    def clear_points_in_frame():
        data = request.json
        session_id = data.get("session_id")
        frame_index = data.get("frame_index")
        object_id = data.get("object_id")
        
        if not all([session_id, frame_index is not None, object_id is not None]):
            return jsonify({"error": "Missing required parameters"}), 400
            
        request_obj = ClearPointsInFrameRequest(
            type="clear_points_in_frame",
            session_id=session_id,
            frame_index=frame_index,
            object_id=object_id,
        )
        
        response = inference_api.clear_points_in_frame(request=request_obj)
        
        return jsonify(RLEMaskListOnFrame(
            frame_index=response.frame_index,
            rle_mask_list=[
                RLEMaskForObject(
                    object_id=r.object_id,
                    rle_mask=RLEMask(counts=r.mask.counts, size=r.mask.size, order="F"),
                )
                for r in response.results
            ],
        ))

    @rest_api.route("/api/clear_points_in_video", methods=["POST"])
    def clear_points_in_video():
        data = request.json
        session_id = data.get("session_id")
        
        if not session_id:
            return jsonify({"error": "Session ID is required"}), 400
            
        request_obj = ClearPointsInVideoRequest(
            type="clear_points_in_video",
            session_id=session_id,
        )
        
        response = inference_api.clear_points_in_video(request=request_obj)
        
        return jsonify(ClearPointsInVideo(success=response.success))

    @rest_api.route("/api/cancel_propagate_in_video", methods=["POST"])
    def cancel_propagate_in_video():
        data = request.json
        session_id = data.get("session_id")
        
        if not session_id:
            return jsonify({"error": "Session ID is required"}), 400
            
        request_obj = CancelPropagateInVideoRequest(
            type="cancel_propagate_in_video",
            session_id=session_id,
        )
        
        response = inference_api.cancel_propagate_in_video(request=request_obj)
        
        return jsonify(CancelPropagateInVideo(success=response.success))
        

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
) -> Tuple[str, str, VideoMetadata]:
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
        except Exception:
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
