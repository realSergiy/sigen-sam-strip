# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import logging
from typing import Dict, Any, List

from flask import Blueprint, jsonify, request
from inference.predictor import InferenceAPI
from inference.data_types import (
    StartSessionRequest,
    CloseSessionRequest,
    AddPointsRequest,
    ClearPointsInFrameRequest,
    ClearPointsInVideoRequest,
    RemoveObjectRequest,
    CancelPropagateInVideoRequest,
)
from app_conf import DATA_PATH

logger = logging.getLogger(__name__)

rest_api = Blueprint('rest_api', __name__)


def create_rest_api(inference_api: InferenceAPI):
    """Create REST API routes with the given inference API instance."""

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
        
        return jsonify({
            "session_id": response.session_id
        })

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
        
        return jsonify({
            "frame_index": response.frame_index,
            "rle_mask_list": [
                {
                    "object_id": r.object_id,
                    "rle_mask": {
                        "counts": r.mask.counts,
                        "size": r.mask.size,
                        "order": "F"
                    }
                }
                for r in response.results
            ]
        })

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
            {
                "frame_index": res.frame_index,
                "rle_mask_list": [
                    {
                        "object_id": r.object_id,
                        "rle_mask": {
                            "counts": r.mask.counts,
                            "size": r.mask.size,
                            "order": "F"
                        }
                    }
                    for r in res.results
                ]
            }
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
        
        return jsonify({
            "frame_index": response.frame_index,
            "rle_mask_list": [
                {
                    "object_id": r.object_id,
                    "rle_mask": {
                        "counts": r.mask.counts,
                        "size": r.mask.size,
                        "order": "F"
                    }
                }
                for r in response.results
            ]
        })

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
        
        return jsonify({
            "success": response.success
        })

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
        
        return jsonify({
            "success": response.success
        })

    return rest_api
