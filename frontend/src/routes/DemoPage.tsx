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
import Toolbar from '@/common/components/toolbar/Toolbar';
import DemoVideoEditor from '@/common/components/video/editor/DemoVideoEditor';
import useInputVideo from '@/common/components/video/useInputVideo';
import StatsView from '@/debug/stats/StatsView';
import {VideoData} from '@/demo/atoms';
import {VIDEO_API_ENDPOINT} from '@/demo/DemoConfig';
import DemoPageLayout from '@/layouts/DemoPageLayout';
import {useEffect, useState, useMemo} from 'react';
import {Location, useLocation} from 'react-router-dom';

type LocationState = {
  video?: VideoData;
};

export default function DemoPage() {
  const {state} = useLocation() as Location<LocationState>;
  const {setInputVideo} = useInputVideo();
  const [defaultVideo, setDefaultVideo] = useState<VideoData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const fetchDefaultVideo = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${VIDEO_API_ENDPOINT}/api/default_video`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setDefaultVideo(data);
      } catch (err) {
        setError(
          err instanceof Error ? err : new Error('Unknown error occurred'),
        );
        console.error('Error fetching default video:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchDefaultVideo();
  }, []);

  const video = useMemo(() => {
    return state?.video ?? defaultVideo;
  }, [state, defaultVideo]);

  useEffect(() => {
    if (video) {
      setInputVideo(video);
    }
  }, [video, setInputVideo]);

  if (loading) {
    return <div>Loading default video...</div>;
  }

  if (error) {
    return <div>Error loading default video: {error.message}</div>;
  }

  if (!video) {
    return <div>No video available</div>;
  }

  return (
    <DemoPageLayout>
      <StatsView />
      <Toolbar />
      <DemoVideoEditor video={video} />
    </DemoPageLayout>
  );
}
