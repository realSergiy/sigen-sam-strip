/**
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import {generateThumbnail} from '@/common/components/video/editor/VideoEditorUtils';
import VideoWorkerContext from '@/common/components/video/VideoWorkerContext';
import Logger from '@/common/logger/Logger';
import {
  BaseTracklet,
  Mask,
  SegmentationPoint,
  StreamingState,
  Tracker,
  Tracklet,
} from '@/common/tracker/Tracker';
import {
  ClearPointsInVideoResponse,
  SessionStartFailedResponse,
  SessionStartedResponse,
  StreamingCompletedResponse,
  StreamingStartedResponse,
  StreamingStateUpdateResponse,
  TrackletCreatedResponse,
  TrackletDeletedResponse,
  TrackletsUpdatedResponse,
} from '@/common/tracker/TrackerTypes';
import {convertMaskToRGBA} from '@/common/utils/MaskUtils';
import multipartStream from '@/common/utils/MultipartStream';
import {Stats} from '@/debug/stats/Stats';
import {INFERENCE_API_ENDPOINT} from '@/demo/DemoConfig';
import {
  DataArray,
  Masks,
  RLEObject,
  decode,
  encode,
  toBbox,
} from '@/jscocotools/mask';
import {THEME_COLORS} from '@/theme/colors';
import invariant from 'invariant';

type Session = {
  id: string | null;
  tracklets: {[id: number]: Tracklet};
};

type StreamMasksResult = {
  frameIndex: number;
  rleMaskList: Array<{
    objectId: number;
    rleMask: RLEObject;
  }>;
  rle_mask_list?: Array<{
    object_id: number;
    rle_mask: {
      counts: string;
      size: number[];
      order: string;
    };
  }>;
};

type StreamMasksAbortResult = {
  aborted: boolean;
};

type RLEMaskListResponse = {
  frameIndex: number;
  rle_mask_list: Array<{
    object_id: number;
    rle_mask: {
      counts: string;
      size: number[];
      order: string;
    };
  }>;
};

export class SAM2Model extends Tracker {
  private _endpoint: string;

  private abortController: AbortController | null = null;
  private _session: Session = {
    id: null,
    tracklets: {},
  };
  private _streamingState: StreamingState = 'none';

  private _emptyMask: RLEObject | null = null;

  private _maskCanvas: OffscreenCanvas;
  private _maskCtx: OffscreenCanvasRenderingContext2D;

  private _stats?: Stats;

  constructor(context: VideoWorkerContext) {
    super(context);
    this._endpoint = INFERENCE_API_ENDPOINT;

    this._maskCanvas = new OffscreenCanvas(0, 0);
    const maskCtx = this._maskCanvas.getContext('2d');
    invariant(maskCtx != null, 'context cannot be null');
    this._maskCtx = maskCtx;
  }

  public async startSession(videoPath: string): Promise<void> {
    // Reset streaming state. Force update with the true flag to make sure the
    // UI updates its state.
    this._updateStreamingState('none', true);

    try {
      const response = await fetch(`${this._endpoint}/api/start_session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          path: videoPath,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      const sessionId = data.session_id;
      this._session.id = sessionId;

      this._sendResponse<SessionStartedResponse>('sessionStarted', {
        sessionId,
      });

      // Clear any tracklets from the previous session when
      // a new session is started
      this._clearTracklets();

      // Make an empty tracklet
      this.createTracklet();
    } catch (error) {
      Logger.error(error);
      this._sendResponse<SessionStartFailedResponse>('sessionStartFailed');
    }
  }

  public async closeSession(): Promise<void> {
    const sessionId = this._session.id;

    // Do not call cleanup before retrieving the session id because cleanup
    // will reset the session id. If the order would be changed, it would
    // never execute the closeSession request.
    this._cleanup();

    if (sessionId === null) {
      return Promise.resolve();
    }

    try {
      const response = await fetch(`${this._endpoint}/api/close_session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      if (data.success === false) {
        throw new Error('Failed to close session');
      }
    } catch (error) {
      Logger.error(error);
      throw error;
    }
  }

  public createTracklet(): void {
    // This will return 0 for for empty tracklets and otherwise the next
    // largest number.
    const nextId =
      Object.values(this._session.tracklets).reduce(
        (prev, curr) => Math.max(prev, curr.id),
        -1,
      ) + 1;

    const newTracklet = {
      id: nextId,
      color: THEME_COLORS[nextId % THEME_COLORS.length],
      thumbnail: null,
      points: [],
      masks: [],
      isInitialized: false,
    };

    this._session.tracklets[nextId] = newTracklet;

    // Notify the main thread
    this._updateTracklets();

    this._sendResponse<TrackletCreatedResponse>('trackletCreated', {
      tracklet: newTracklet,
    });
  }

  public async deleteTracklet(trackletId: number): Promise<void> {
    const sessionId = this._session.id;
    if (sessionId === null) {
      return Promise.reject('No active session');
    }

    const tracklet = this._session.tracklets[trackletId];
    invariant(
      tracklet != null,
      'tracklet for tracklet id %s not initialized',
      trackletId,
    );

    try {
      const response = await fetch(`${this._endpoint}/api/remove_object`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          object_id: trackletId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const trackletUpdates = await response.json();
      this._sendResponse<TrackletDeletedResponse>('trackletDeleted', {
        isSuccessful: true,
      });

      for (const trackletUpdate of trackletUpdates) {
        this._updateTrackletMasks(
          trackletUpdate,
          trackletUpdate.frameIndex === this._context.frameIndex,
          false, // shouldGoToFrame
        );
      }

      this._removeTrackletMasks(tracklet);
    } catch (error) {
      this._sendResponse<TrackletDeletedResponse>('trackletDeleted', {
        isSuccessful: false,
      });
      Logger.error(error);
      throw error;
    }
  }

  public async updatePoints(
    frameIndex: number,
    objectId: number,
    points: SegmentationPoint[],
  ): Promise<void> {
    const sessionId = this._session.id;
    if (sessionId === null) {
      return Promise.reject('No active session');
    }

    // TODO: This is not the right place to initialize the empty mask.
    // Move this into the constructor and listen to events on the context.
    // Note, the initial context.width and context.height is 0, so it needs
    // to happen based on an event, so when the video is initialized, it needs
    // to notify the tracker to update the empty mask.
    if (this._emptyMask === null) {
      // We need to round the height/width to the nearest integer since
      // Masks.toTensor() expects an integer value for the height/width.
      const tensor = new Masks(
        Math.trunc(this._context.height),
        Math.trunc(this._context.width),
        1,
      ).toDataArray();
      this._emptyMask = encode(tensor)[0];
    }

    const tracklet = this._session.tracklets[objectId];
    invariant(
      tracklet != null,
      'tracklet for object id %s not initialized',
      objectId,
    );

    // Mark session needing propagation when point is set
    this._updateStreamingState('required');

    // Clear all points in frame if no points are provided.
    if (points.length === 0) {
      return this.clearPointsInFrame(frameIndex, objectId);
    }

    try {
      const normalizedPoints = points.map(p => [
        p[0] / this._context.width,
        p[1] / this._context.height,
      ]);
      const labels = points.map(p => p[2]);

      const response = await fetch(`${this._endpoint}/api/add_points`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          session_id: sessionId,
          frame_index: frameIndex,
          object_id: objectId,
          labels: labels,
          points: normalizedPoints,
          clear_old_points: true,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      tracklet.points[frameIndex] = points;
      tracklet.isInitialized = true;
      this._updateTrackletMasks(data, true);
    } catch (error) {
      Logger.error(error);
      throw error;
    }
  }

  public async clearPointsInFrame(
    frameIndex: number,
    objectId: number,
  ): Promise<void> {
    const sessionId = this._session.id;
    if (sessionId === null) {
      return Promise.reject('No active session');
    }

    const tracklet = this._session.tracklets[objectId];
    invariant(
      tracklet != null,
      'tracklet for object id %s not initialized',
      objectId,
    );

    // Mark session needing propagation when point is set
    this._updateStreamingState('required');

    try {
      const response = await fetch(
        `${this._endpoint}/api/clear_points_in_frame`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: sessionId,
            frame_index: frameIndex,
            object_id: objectId,
          }),
        },
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      tracklet.points[frameIndex] = [];
      tracklet.isInitialized = true;
      this._updateTrackletMasks(data, true);
    } catch (error) {
      Logger.error(error);
      throw error;
    }
  }

  public async clearPointsInVideo(): Promise<void> {
    const sessionId = this._session.id;
    if (sessionId === null) {
      return Promise.reject('No active session');
    }

    // Mark session needing propagation when point is set
    this._updateStreamingState('none');

    try {
      const response = await fetch(
        `${this._endpoint}/api/clear_points_in_video`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: sessionId,
          }),
        },
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      const {success} = data;

      if (!success) {
        this._sendResponse<ClearPointsInVideoResponse>('clearPointsInVideo', {
          isSuccessful: false,
        });
        return;
      }

      // Reset points and masks for each tracklet
      this._clearTracklets();

      // Notify the main thread
      this._context.goToFrame(this._context.frameIndex);
      this._updateTracklets();
      this._sendResponse<ClearPointsInVideoResponse>('clearPointsInVideo', {
        isSuccessful: true,
      });
    } catch (error) {
      this._sendResponse<ClearPointsInVideoResponse>('clearPointsInVideo', {
        isSuccessful: false,
      });
      Logger.error(error);
    }
  }

  public async streamMasks(frameIndex: number): Promise<void> {
    const sessionId = this._session.id;
    if (sessionId === null) {
      return Promise.reject('No active session');
    }
    try {
      this._sendResponse<StreamingStartedResponse>('streamingStarted');

      // 1. Clear previous masks
      this._context.clearMasks();
      this._clearTrackletMasks();

      // 2. Create abort controller and async generator
      const controller = new AbortController();
      this.abortController = controller;

      this._updateStreamingState('requesting');
      const generator = this._streamMasksForSession(
        controller,
        sessionId,
        frameIndex,
      );

      // 3. parse stream response and update masks in session objects
      let isAborted = false;
      for await (const result of generator) {
        if ('aborted' in result) {
          this._updateStreamingState('aborting');
          await this._abortRequest();
          this._updateStreamingState('aborted');
          isAborted = true;
        } else {
          // Convert StreamMasksResult to RLEMaskListResponse format
          const maskListResponse: RLEMaskListResponse = {
            frameIndex: result.frameIndex,
            rle_mask_list: result.rleMaskList.map(item => ({
              object_id: item.objectId,
              rle_mask: {
                counts: item.rleMask.counts,
                size: item.rleMask.size,
                order: 'F',
              },
            })),
          };
          await this._updateTrackletMasks(maskListResponse, false);
          this._updateStreamingState('partial');
        }
      }

      if (!isAborted) {
        // Mark session needing propagation when point is set
        this._updateStreamingState('full');
      }
    } catch (error) {
      Logger.error(error);
      throw error;
    }

    this._sendResponse<StreamingCompletedResponse>('streamingCompleted');
  }

  public abortStreamMasks() {
    this.abortController?.abort();
    this._sendResponse<StreamingCompletedResponse>('streamingCompleted');
  }

  public enableStats(): void {
    this._stats = new Stats('ms', 'D', 1000 / 25);
  }

  // PRIVATE

  private _cleanup() {
    this._session.id = null;
    // Clear existing tracklets
    this._session.tracklets = [];
  }

  private _clearTracklets() {
    this._session.tracklets = [];
    this._context.clearMasks();
  }

  private _updateStreamingState(
    state: StreamingState,
    forceUpdate: boolean = false,
  ) {
    if (!forceUpdate && this._streamingState === state) {
      return;
    }
    this._streamingState = state;
    this._sendResponse<StreamingStateUpdateResponse>('streamingStateUpdate', {
      state,
    });
  }

  private async _removeTrackletMasks(tracklet: Tracklet) {
    this._context.clearTrackletMasks(tracklet);
    delete this._session.tracklets[tracklet.id];

    // Notify the main thread
    this._context.goToFrame(this._context.frameIndex);
    this._updateTracklets();
  }

  private async _updateTrackletMasks(
    data: RLEMaskListResponse,
    updateThumbnails: boolean,
    shouldGoToFrame: boolean = true,
  ) {
    const {frameIndex, rle_mask_list} = data;

    // 1. parse and decode masks for all objects
    for (const {object_id, rle_mask} of rle_mask_list) {
      const track = this._session.tracklets[object_id];
      const {size, counts} = rle_mask;
      const rleObject: RLEObject = {
        size: [size[0], size[1]],
        counts: counts,
      };
      const isEmpty = counts === this._emptyMask?.counts;

      this._stats?.begin();

      const decodedMask = decode([rleObject]);
      const bbox = toBbox([rleObject]);

      const mask: Mask = {
        data: rleObject as RLEObject,
        shape: [...decodedMask.shape],
        bounds: [
          [bbox[0], bbox[1]],
          [bbox[0] + bbox[2], bbox[1] + bbox[3]],
        ],
        isEmpty,
      } as const;
      track.masks[frameIndex] = mask;

      if (updateThumbnails && !isEmpty) {
        const {ctx} = await this._compressMaskForCanvas(decodedMask);
        const frame = this._context.currentFrame as VideoFrame;
        await generateThumbnail(track, frameIndex, mask, frame, ctx);
      }
    }

    this._context.updateTracklets(
      frameIndex,
      Object.values(this._session.tracklets),
      shouldGoToFrame,
    );

    // Notify the main thread
    this._updateTracklets();
  }

  private _updateTracklets() {
    const tracklets: BaseTracklet[] = Object.values(
      this._session.tracklets,
    ).map(tracklet => {
      // Notify the main thread
      const {
        id,
        color,
        isInitialized,
        points: trackletPoints,
        thumbnail,
        masks,
      } = tracklet;
      return {
        id,
        color,
        isInitialized,
        points: trackletPoints,
        thumbnail,
        masks: masks.map(mask => ({
          shape: mask.shape,
          bounds: mask.bounds,
          isEmpty: mask.isEmpty,
        })),
      };
    });

    this._sendResponse<TrackletsUpdatedResponse>('trackletsUpdated', {
      tracklets,
    });
  }

  private _clearTrackletMasks() {
    const keys = Object.keys(this._session.tracklets);
    for (const key of keys) {
      const trackletId = Number(key);
      const tracklet = {...this._session.tracklets[trackletId], masks: []};
      this._session.tracklets[trackletId] = tracklet;
    }
    this._updateTracklets();
  }

  private async _compressMaskForCanvas(
    decodedMask: DataArray,
  ): Promise<{compressedData: Blob; ctx: OffscreenCanvasRenderingContext2D}> {
    const data = convertMaskToRGBA(decodedMask.data as Uint8Array);

    this._maskCanvas.width = decodedMask.shape[0];
    this._maskCanvas.height = decodedMask.shape[1];

    const imageData = new ImageData(
      data,
      decodedMask.shape[0],
      decodedMask.shape[1],
    );
    this._maskCtx.putImageData(imageData, 0, 0);

    const canvas = new OffscreenCanvas(
      decodedMask.shape[1],
      decodedMask.shape[0],
    );

    const ctx = canvas.getContext('2d');
    invariant(ctx != null, 'context cannot be null');
    ctx.save();
    ctx.rotate(Math.PI / 2);
    // Since the image was previously rotated 90° clockwise, after the image is rotated,
    // we scale the canvas's width using scaleY and height using scaleX.
    ctx.scale(1, -1);
    ctx.drawImage(this._maskCanvas, 0, 0);
    ctx.restore();

    const compressedData = await canvas.convertToBlob({type: 'image/png'});

    return {compressedData, ctx};
  }

  private async *_streamMasksForSession(
    abortController: AbortController,
    sessionId: string,
    startFrameIndex: undefined | number = 0,
  ): AsyncGenerator<StreamMasksResult | StreamMasksAbortResult, undefined> {
    const url = `${this._endpoint}/propagate_in_video`;

    const requestBody = {
      session_id: sessionId,
      start_frame_index: startFrameIndex,
    };

    const headers: {[name: string]: string} = Object.assign({
      'Content-Type': 'application/json',
    });

    const response = await fetch(url, {
      method: 'POST',
      body: JSON.stringify(requestBody),
      headers,
    });

    const contentType = response.headers.get('Content-Type');
    if (
      contentType == null ||
      !contentType.startsWith('multipart/x-savi-stream;')
    ) {
      throw new Error(
        'endpoint needs to support Content-Type "multipart/x-savi-stream"',
      );
    }

    const responseBody = response.body;
    if (responseBody == null) {
      throw new Error('response body is null');
    }

    const reader = multipartStream(contentType, responseBody).getReader();

    const textDecoder = new TextDecoder();

    while (true) {
      if (abortController.signal.aborted) {
        reader.releaseLock();
        yield {aborted: true};
        return;
      }

      const {done, value} = await reader.read();
      if (done) {
        return;
      }

      const {headers, body} = value;

      const contentType = headers.get('Content-Type') as string;

      if (contentType.startsWith('application/json')) {
        const jsonResponse = JSON.parse(textDecoder.decode(body));
        const maskResults = jsonResponse.results;
        const rleMaskList = maskResults.map(
          (mask: {object_id: number; mask: RLEObject}) => {
            return {
              objectId: mask.object_id,
              rleMask: mask.mask,
            };
          },
        );
        yield {
          frameIndex: jsonResponse.frame_index,
          rleMaskList,
        };
      }
    }
  }

  private async _abortRequest(): Promise<void> {
    const sessionId = this._session.id;
    invariant(sessionId != null, 'session id cannot be empty');

    try {
      const response = await fetch(
        `${this._endpoint}/api/cancel_propagate_in_video`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: sessionId,
          }),
        },
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      const {success} = data;

      if (!success) {
        throw new Error(`could not abort session ${sessionId}`);
      }
    } catch (error) {
      Logger.error(error);
      throw error;
    }
  }
}
