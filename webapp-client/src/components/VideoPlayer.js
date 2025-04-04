import React, { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import '../styles/VideoPlayer.css';
// Import icons
import { FaBroadcastTower } from 'react-icons/fa';

const VideoPlayer = ({ isLiveMode, selectedRecording, onSwitchToLive, onStreamStateChange }) => {
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(true);
  const [seekError, setSeekError] = useState(false);
  const [availableRange, setAvailableRange] = useState({ start: 0, end: 0 });
  const [streamReady, setStreamReady] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const hlsUrl = process.env.REACT_APP_HLS_STREAM_URL;
  const playAttemptRef = useRef(0);
  const streamStateRef = useRef(false);

  const attemptPlay = async () => {
    const video = videoRef.current;
    if (!video || !streamReady) return;
    
    try {
      await video.play();
      setError(null);
      setIsPlaying(true);
      if (isLiveMode && !streamStateRef.current) {
        streamStateRef.current = true;
        onStreamStateChange(true);
      }
    } catch (error) {
      console.log('Play attempted before stream was ready, waiting...');
      if (playAttemptRef.current >= 2) {
        console.error('Multiple play attempts failed:', error);
        setError('Failed to start playback. Please try again.');
      }
      playAttemptRef.current++;
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let hls;
    let isDestroyed = false;
    let retryTimeout = null;

    const initializePlayer = async () => {
      if (isDestroyed) return;
      setIsLoading(true);
      setError(null);
      playAttemptRef.current = 0;

      try {
        const sourceUrl = isLiveMode ? hlsUrl : selectedRecording?.streamUrl;
        const isHLS = isLiveMode || (selectedRecording?.format === 'hls');

        if (!sourceUrl) {
          console.error('No source URL available');
          setError('Stream URL not available');
          setIsLoading(false);
          return;
        }

        if (isHLS && Hls.isSupported()) {
          hls = new Hls({
            enableWorker: true,
            lowLatencyMode: isLiveMode,
            backBufferLength: 90,
            liveDurationInfinity: isLiveMode,
            liveBackBufferLength: isLiveMode ? 300 : null,
            fragLoadingMaxRetry: 6,
            fragLoadingRetryDelay: 500,
            manifestLoadingMaxRetry: 6,
            manifestLoadingRetryDelay: 500,
            debug: true
          });

          hlsRef.current = hls;

          hls.on(Hls.Events.ERROR, (event, data) => {
            console.error('HLS error:', {
              type: data.type,
              details: data.details,
              fatal: data.fatal,
              error: data.error
            });

            if (data.fatal) {
              switch (data.type) {
                case Hls.ErrorTypes.NETWORK_ERROR:
                  console.error('HLS network error - attempting to recover');
                  hls.startLoad();
                  break;
                case Hls.ErrorTypes.MEDIA_ERROR:
                  console.error('HLS media error - attempting to recover');
                  hls.recoverMediaError();
                  break;
                default:
                  console.error('HLS fatal error - cannot recover');
                  setError('Stream not available. Please try again later.');
                  if (isLiveMode && streamStateRef.current) {
                    streamStateRef.current = false;
                    onStreamStateChange(false);
                  }
                  break;
              }
            }
          });

          hls.on(Hls.Events.MANIFEST_LOADING, () => {
            console.log('HLS: Manifest loading started');
          });

          hls.on(Hls.Events.MANIFEST_LOADED, (event, data) => {
            console.log('HLS: Manifest loaded:', data);
          });

          hls.on(Hls.Events.MANIFEST_PARSED, (event, data) => {
            console.log('HLS: Manifest parsed:', data);
            setStreamReady(true);
            setIsLoading(false);
            attemptPlay();
          });

          hls.on(Hls.Events.FRAG_LOADING, (event, data) => {
            console.log('HLS: Loading fragment:', data.frag.url);
          });

          hls.on(Hls.Events.FRAG_LOADED, (event, data) => {
            console.log('HLS: Fragment loaded:', data.frag.url);
            setError(null);
            playAttemptRef.current = 0;
          });

          hls.on(Hls.Events.FRAG_ERROR, (event, data) => {
            console.error('HLS: Fragment error:', {
              url: data.frag.url,
              details: data.details,
              error: data.error
            });
          });

          hls.loadSource(sourceUrl);
          hls.attachMedia(video);
        } else {
          video.src = sourceUrl;
          video.addEventListener('loadedmetadata', () => {
            console.log('Video metadata loaded (native HLS)');
            setStreamReady(true);
            setIsLoading(false);
            attemptPlay();
          });

          video.addEventListener('error', (e) => {
            console.error('Video error (native HLS):', {
              error: video.error,
              code: video.error?.code,
              message: video.error?.message
            });
            setError('Stream not available. Please try again later.');
            if (isLiveMode && streamStateRef.current) {
              streamStateRef.current = false;
              onStreamStateChange(false);
            }
          });
        }
      } catch (error) {
        console.error('Error initializing player:', error);
        setError('Failed to initialize video player.');
        setIsLoading(false);
      }
    };

    const destroyPlayer = () => {
      console.log('Destroying player');
      isDestroyed = true;
      if (retryTimeout) {
        clearTimeout(retryTimeout);
      }
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
      if (video) {
        video.src = '';
        video.load();
      }
      setStreamReady(false);
      playAttemptRef.current = 0;
      if (isLiveMode && streamStateRef.current) {
        streamStateRef.current = false;
        onStreamStateChange(false);
      }
    };

    console.log('VideoPlayer effect running with:', {
      isLiveMode,
      selectedRecording,
      hasHlsUrl: !!hlsUrl
    });

    initializePlayer();

    return () => {
      destroyPlayer();
    };
  }, [isLiveMode, selectedRecording, hlsUrl, onStreamStateChange]);

  return (
    <div className="video-player-container">
      <div className="video-wrapper">
        <video
          ref={videoRef}
          controls
          playsInline
          className="video-element"
          autoPlay
          muted
        />
        {isLoading && (
          <div className="loading-overlay">
            <div className="loading-spinner"></div>
            <div>Loading {isLiveMode ? 'live stream' : 'recording'}...</div>
          </div>
        )}
        {error && (
          <div className="error-overlay">
            <div className="error-message">{error}</div>
            <button className="retry-button" onClick={() => window.location.reload()}>
              Retry
            </button>
          </div>
        )}
      </div>
      <div className="controls">
        {!isLiveMode && (
          <button 
            className="control-button"
            onClick={onSwitchToLive}
            title="Switch to Live Stream"
          >
            <FaBroadcastTower /> Switch to Live
          </button>
        )}
      </div>
      {selectedRecording && !isLiveMode && (
        <div className="recording-info">
          <h3>{selectedRecording.stream_name}</h3>
          <p>Recorded: {new Date(selectedRecording.created_at).toLocaleString()}</p>
          {selectedRecording.duration && (
            <p>Duration: {Math.floor(selectedRecording.duration / 60)}:{(selectedRecording.duration % 60).toString().padStart(2, '0')}</p>
          )}
        </div>
      )}
    </div>
  );
};

export default VideoPlayer; 