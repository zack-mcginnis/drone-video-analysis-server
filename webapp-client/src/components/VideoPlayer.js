import React, { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import '../styles/VideoPlayer.css';
// Import icons
import { FaStepBackward, FaBroadcastTower } from 'react-icons/fa';

const VideoPlayer = () => {
  const videoRef = useRef(null);
  const hlsRef = useRef(null);
  const [isLive, setIsLive] = useState(true);
  const [isPlaying, setIsPlaying] = useState(true);
  const [seekError, setSeekError] = useState(false);
  const [availableRange, setAvailableRange] = useState({ start: 0, end: 0 });
  const [streamReady, setStreamReady] = useState(false);
  const hlsUrl = process.env.REACT_APP_HLS_STREAM_URL;

  useEffect(() => {
    const video = videoRef.current;
    
    if (!video) return;

    let hls;
    let errorCount = 0;
    const MAX_ERRORS = 3;
    let isDestroyed = false;
    let retryTimeout = null;

    const initializePlayer = () => {
      if (isDestroyed) return;
      
      if (Hls.isSupported()) {
        hls = new Hls({
          enableWorker: true,
          lowLatencyMode: true,
          backBufferLength: 90,
          liveDurationInfinity: true,
          liveBackBufferLength: 300, // 5 minutes
          // Add a small buffer to avoid constant seeking errors
          fragLoadingMaxRetry: 6,
          fragLoadingRetryDelay: 500,
          manifestLoadingMaxRetry: 6,
          manifestLoadingRetryDelay: 500
        });
        
        hlsRef.current = hls;
        
        hls.loadSource(hlsUrl);
        hls.attachMedia(video);
        
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          setStreamReady(true);
          // Set to highest quality level by default
          hls.currentLevel = hls.levels.length - 1; // Force highest quality
          
          video.play().catch(error => {
            console.error('Error attempting to play:', error);
          });
        });
        
        // Track available segments
        hls.on(Hls.Events.LEVEL_UPDATED, (_, data) => {
          if (data.details && data.details.fragments && data.details.fragments.length > 0) {
            const fragments = data.details.fragments;
            const start = fragments[0].start;
            const end = fragments[fragments.length - 1].start + fragments[fragments.length - 1].duration;
            setAvailableRange({ start, end });
          }
        });

        hls.on(Hls.Events.ERROR, (event, data) => {
          if (data.fatal) {
            switch (data.type) {
              case Hls.ErrorTypes.NETWORK_ERROR:
                console.log('Network error, trying to recover...');
                errorCount++;
                
                // Special handling for initial 404 errors (stream not ready yet)
                if (data.response && data.response.code === 404 && !streamReady) {
                  console.log('Stream not ready yet, retrying in 2 seconds...');
                  clearTimeout(retryTimeout);
                  retryTimeout = setTimeout(() => {
                    if (hls) {
                      hls.destroy();
                    }
                    initializePlayer();
                  }, 2000);
                  return;
                }
                
                if (errorCount > MAX_ERRORS) {
                  // Too many errors, jump to live
                  console.log('Too many errors, jumping to live');
                  setSeekError(true);
                  safeJumpToLive();
                  errorCount = 0;
                } else {
                  hls.startLoad();
                }
                break;
              case Hls.ErrorTypes.MEDIA_ERROR:
                console.log('Media error, trying to recover...');
                hls.recoverMediaError();
                break;
              default:
                // Only destroy and reinitialize if not already destroyed
                if (!isDestroyed) {
                  console.error('Fatal error, destroying HLS instance:', data);
                  isDestroyed = true;
                  hls.destroy();
                  // Small delay before reinitializing
                  setTimeout(() => {
                    isDestroyed = false;
                    initializePlayer();
                  }, 1000);
                }
                break;
            }
          } else if (data.details === Hls.ErrorDetails.BUFFER_SEEK_OVER_HOLE) {
            // This happens when seeking to a point where data is missing
            console.log('Seek error, jumping to live');
            setSeekError(true);
            safeJumpToLive();
          }
        });
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        // For Safari
        video.src = hlsUrl;
        video.addEventListener('loadedmetadata', () => {
          video.play().catch(error => {
            console.error('Error attempting to play:', error);
          });
        });
      }
    };

    initializePlayer();

    // Check if we're at the live edge
    const checkLiveStatus = () => {
      if (!video || !hlsRef.current) return;
      
      const hls = hlsRef.current;
      
      if (video.readyState > 0 && !video.paused) {
        let isAtLiveEdge = false;
        
        // Method 1: Check using liveSyncPosition (most accurate)
        if (hls.liveSyncPosition) {
          const liveEdgeThreshold = 3.0; // 3 seconds threshold
          isAtLiveEdge = Math.abs(video.currentTime - hls.liveSyncPosition) < liveEdgeThreshold;
        } 
        // Method 2: Check using duration (less accurate but works as fallback)
        else if (isFinite(video.duration)) {
          isAtLiveEdge = video.duration - video.currentTime < 10;
        }
        // Method 3: Check using availableRange (another fallback)
        else if (availableRange.end > 0) {
          isAtLiveEdge = Math.abs(video.currentTime - availableRange.end) < 5;
        }
        
        // Debug info
        if (process.env.NODE_ENV === 'development') {
          console.debug('Live status check:', {
            currentTime: video.currentTime,
            liveSyncPosition: hls.liveSyncPosition,
            duration: video.duration,
            availableRangeEnd: availableRange.end,
            isAtLiveEdge
          });
        }
        
        setIsLive(isAtLiveEdge);
        setIsPlaying(!video.paused);
        
        // Reset seek error when we're back at live edge
        if (isAtLiveEdge && seekError) {
          setSeekError(false);
        }
      }
    };

    const intervalId = setInterval(checkLiveStatus, 1000);

    // Clean up
    return () => {
      clearInterval(intervalId);
      clearTimeout(retryTimeout);
      if (hlsRef.current) {
        hlsRef.current.destroy();
      }
    };
  }, [hlsUrl, seekError]);

  const safeJumpToLive = () => {
    const video = videoRef.current;
    const hls = hlsRef.current;
    
    if (!video || !hls) return;
    
    try {
      // First, try using HLS.js's liveSyncPosition which is the most reliable way
      // to get the live edge position
      if (hls.liveSyncPosition) {
        console.log('Jumping to liveSyncPosition:', hls.liveSyncPosition);
        video.currentTime = hls.liveSyncPosition;
      } 
      // If liveSyncPosition is not available, try using the end of the available range
      else if (availableRange.end > 0) {
        console.log('Jumping to availableRange.end:', availableRange.end);
        video.currentTime = availableRange.end - 1; // Slightly before the end
      }
      // If neither is available, try using video.duration
      else if (video.duration && isFinite(video.duration)) {
        console.log('Jumping to video.duration:', video.duration);
        video.currentTime = video.duration - 1; // Slightly before the end
      } 
      // Last resort: reload the stream from the latest fragment
      else {
        console.log('No valid position found, reloading stream from latest fragment');
        hls.stopLoad();
        hls.startLoad(-1); // -1 means start loading from the latest fragment
      }
      
      // Resume playback if paused
      if (video.paused) {
        video.play().catch(error => {
          console.error('Error attempting to play:', error);
        });
      }
      
      // Force HLS to move to live edge
      hls.streamController.nextLoadPosition = hls.liveSyncPosition;
      
    } catch (error) {
      console.error('Error jumping to live:', error);
      // If direct seeking fails, try to reload the player from the latest fragment
      if (hls) {
        console.log('Error recovery: reloading from latest fragment');
        hls.stopLoad();
        hls.startLoad(-1);
      }
    }
  };

  const jumpToLive = () => {
    safeJumpToLive();
    setSeekError(false);
  };

  const jumpToBeginning = () => {
    const video = videoRef.current;
    if (video && availableRange.start > 0) {
      try {
        // Jump to the earliest available point in the stream
        video.currentTime = availableRange.start + 1; // Add a small buffer
        // Resume playback if paused
        if (video.paused) {
          video.play().catch(error => {
            console.error('Error attempting to play:', error);
          });
        }
      } catch (error) {
        console.error('Error seeking to beginning:', error);
        setSeekError(true);
      }
    } else {
      // If we don't know the available range yet, try seeking to 0
      try {
        video.currentTime = 0;
        if (video.paused) {
          video.play().catch(error => {
            console.error('Error attempting to play:', error);
          });
        }
      } catch (error) {
        console.error('Error seeking to beginning:', error);
        setSeekError(true);
      }
    }
  };

  return (
    <div className="video-container">
      {!streamReady && (
        <div className="loading-overlay">
          <div className="loading-spinner"></div>
          <p>Waiting for stream...</p>
        </div>
      )}
      
      <div className="video-wrapper">
        <video 
          ref={videoRef} 
          className="video-player" 
          controls 
          playsInline
          muted
        />
        
        <div className="custom-controls">
          <button 
            className="control-button beginning-button"
            onClick={jumpToBeginning}
            title="Jump to Beginning"
          >
            <FaStepBackward />
          </button>
          
          <button 
            className={`control-button live-button ${isLive ? 'active' : ''}`}
            onClick={jumpToLive}
            title="Jump to Live"
          >
            <FaBroadcastTower />
            <span className="live-indicator">LIVE</span>
          </button>
        </div>
      </div>
      
      {seekError && (
        <div className="seek-error-message">
          Previous segments no longer available. Please watch the live stream.
        </div>
      )}
      
      <div className="video-info">
        <div className="stream-status">
          <div className={`status-indicator ${isLive && isPlaying ? 'live' : 'delayed'}`}></div>
          <span>{isLive && isPlaying ? 'LIVE' : 'DELAYED'}</span>
        </div>
      </div>
    </div>
  );
};

export default VideoPlayer; 