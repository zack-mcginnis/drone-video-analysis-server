import React, { useEffect, useRef } from 'react';
import Hls from 'hls.js';
import '../styles/VideoPlayer.css';

const VideoPlayer = () => {
  const videoRef = useRef(null);
  const hlsUrl = process.env.REACT_APP_HLS_STREAM_URL;

  useEffect(() => {
    let hls;
    
    const initPlayer = () => {
      if (Hls.isSupported()) {
        hls = new Hls({
          enableWorker: true,
          lowLatencyMode: true,
          backBufferLength: 90
        });
        
        hls.loadSource(hlsUrl);
        hls.attachMedia(videoRef.current);
        
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          videoRef.current.play().catch(error => {
            console.error('Error attempting to play', error);
          });
        });
        
        hls.on(Hls.Events.ERROR, (event, data) => {
          if (data.fatal) {
            switch (data.type) {
              case Hls.ErrorTypes.NETWORK_ERROR:
                console.log('Network error, trying to recover...');
                hls.startLoad();
                break;
              case Hls.ErrorTypes.MEDIA_ERROR:
                console.log('Media error, trying to recover...');
                hls.recoverMediaError();
                break;
              default:
                console.error('Fatal error, destroying HLS instance');
                hls.destroy();
                initPlayer();
                break;
            }
          }
        });
      } else if (videoRef.current.canPlayType('application/vnd.apple.mpegurl')) {
        // For Safari which has built-in HLS support
        videoRef.current.src = hlsUrl;
        videoRef.current.addEventListener('loadedmetadata', () => {
          videoRef.current.play().catch(error => {
            console.error('Error attempting to play', error);
          });
        });
      } else {
        console.error('HLS is not supported in this browser');
      }
    };

    if (videoRef.current) {
      initPlayer();
    }

    return () => {
      if (hls) {
        hls.destroy();
      }
    };
  }, [hlsUrl]);

  return (
    <div className="video-container">
      <video 
        ref={videoRef} 
        controls 
        playsInline
        muted
        className="video-player"
      />
      <div className="video-info">
        <p>Stream URL: {hlsUrl}</p>
        <p>Status: <span className="status-indicator">Live</span></p>
      </div>
    </div>
  );
};

export default VideoPlayer; 