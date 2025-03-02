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
import VideoGalleryUploadVideo from '@/common/components/gallery/VideoGalleryUploadPhoto';
import VideoPhoto from '@/common/components/gallery/VideoPhoto';
import useScreenSize from '@/common/screen/useScreenSize';
import {VideoData} from '@/demo/atoms';
import {DEMO_SHORT_NAME, VIDEO_API_ENDPOINT} from '@/demo/DemoConfig';
import {fontSize, fontWeight, spacing} from '@/theme/tokens.stylex';
import stylex from '@stylexjs/stylex';
import {useEffect, useState} from 'react';
import PhotoAlbum, {Photo, RenderPhotoProps} from 'react-photo-album';
import {useLocation, useNavigate} from 'react-router-dom';

const styles = stylex.create({
  container: {
    display: 'flex',
    flexDirection: 'column',
    marginHorizontal: spacing[1],
    height: '100%',
    lineHeight: 1.2,
    paddingTop: spacing[8],
  },
  headerContainer: {
    marginBottom: spacing[8],
    fontWeight: fontWeight['medium'],
    fontSize: fontSize['2xl'],
    '@media screen and (max-width: 768px)': {
      marginTop: spacing[0],
      marginBottom: spacing[8],
      marginHorizontal: spacing[4],
      fontSize: fontSize['xl'],
    },
  },
  albumContainer: {
    flex: '1 1 0%',
    width: '100%',
    overflowY: 'auto',
  },
});

type Props = {
  showUploadInGallery?: boolean;
  onSelect?: (video: VideoPhotoData) => void;
  onUpload: (video: VideoData) => void;
  onUploadStart?: () => void;
  onUploadError?: (error: Error) => void;
};

type VideoPhotoData = Photo &
  VideoData & {
    poster: string;
    isUploadOption: boolean;
  };

export default function DemoVideoGallery({
  showUploadInGallery = false,
  onSelect,
  onUpload,
  onUploadStart,
  onUploadError,
}: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const {isMobile: isMobileScreenSize} = useScreenSize();
  const [videos, setVideos] = useState<VideoPhotoData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const fetchVideos = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${VIDEO_API_ENDPOINT}/api/videos`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();

        const videoData = data.map((video: any) => {
          return {
            src: video.url,
            path: video.path,
            poster: video.posterPath,
            posterPath: video.posterPath,
            url: video.url,
            posterUrl: video.posterUrl,
            width: video.width,
            height: video.height,
            isUploadOption: false,
          } as VideoPhotoData;
        });

        setVideos(videoData);
      } catch (err) {
        setError(
          err instanceof Error ? err : new Error('Unknown error occurred'),
        );
        console.error('Error fetching videos:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchVideos();
  }, []);

  const shareableVideos: VideoPhotoData[] = (() => {
    const filteredVideos = [...videos];

    if (showUploadInGallery) {
      const uploadOption = {
        src: '',
        width: 1280,
        height: 720,
        poster: '',
        isUploadOption: true,
      } as VideoPhotoData;
      filteredVideos.unshift(uploadOption);
    }

    return filteredVideos;
  })();

  const renderPhoto = ({
    photo: video,
    imageProps,
  }: RenderPhotoProps<VideoPhotoData>) => {
    const {style} = imageProps;
    const {url, posterUrl} = video;

    return video.isUploadOption ? (
      <VideoGalleryUploadVideo
        style={style}
        onUpload={handleUploadVideo}
        onUploadError={onUploadError}
        onUploadStart={onUploadStart}
      />
    ) : (
      <VideoPhoto
        src={url}
        poster={posterUrl}
        style={style}
        onClick={() => {
          navigate(location.pathname, {
            state: {
              video,
            },
          });
          onSelect?.(video);
        }}
      />
    );
  };

  function handleUploadVideo(video: VideoData) {
    navigate(location.pathname, {
      state: {
        video,
      },
    });
    onUpload?.(video);
  }

  const descriptionStyle = 'text-sm md:text-base text-gray-400 leading-snug';

  if (loading) {
    return <div>Loading videos...</div>;
  }

  if (error) {
    return <div>Error loading videos: {error.message}</div>;
  }

  return (
    <div {...stylex.props(styles.container)}>
      <div {...stylex.props(styles.albumContainer)}>
        <div className="pt-0 md:px-16 md:pt-8 md:pb-8">
          <div {...stylex.props(styles.headerContainer)}>
            <h3 className="mb-2">
              Select a video to try{' '}
              <span className="hidden md:inline">
                with the {DEMO_SHORT_NAME}
              </span>
            </h3>
            <p className={descriptionStyle}>
              You'll be able to download what you make.
            </p>
          </div>

          <PhotoAlbum<VideoPhotoData>
            layout="rows"
            photos={shareableVideos}
            targetRowHeight={isMobileScreenSize ? 120 : 200}
            rowConstraints={{
              singleRowMaxHeight: isMobileScreenSize ? 120 : 240,
              maxPhotos: 3,
            }}
            renderPhoto={renderPhoto}
            spacing={4}
          />
        </div>
      </div>
    </div>
  );
}
