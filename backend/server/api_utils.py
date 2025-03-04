import hashlib
import os
import shutil
import tempfile
import av
from werkzeug.datastructures import FileStorage
from backend.server.app import _get_start_sec_duration_sec
from backend.server.app_conf import UPLOADS_PATH, UPLOADS_PREFIX
from backend.server.data.transcoder import VideoMetadata, get_video_metadata, transcode
from typing import Optional, Tuple, Union


def get_file_hash(video_path_or_file) -> str:
    if isinstance(video_path_or_file, str):
        with open(video_path_or_file, "rb") as in_f:
            result = hashlib.sha256(in_f.read()).hexdigest()
    else:
        video_path_or_file.seek(0)
        result = hashlib.sha256(video_path_or_file.read()).hexdigest()
    return result

# Helper functions for video processing
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