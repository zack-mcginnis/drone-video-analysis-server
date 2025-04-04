import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { FaPlay, FaClock, FaCalendarAlt, FaVideo } from 'react-icons/fa';
import '../styles/RecordingsList.css';

const RecordingsList = ({ onSelectRecording, streamState }) => {
  const [recordings, setRecordings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(Date.now());

  const fetchRecordings = async () => {
    try {
      const response = await axios.get(`${process.env.REACT_APP_API_URL}/recordings`);
      setRecordings(response.data.recordings);
      setLoading(false);
      setError(null);
    } catch (err) {
      setError('Failed to fetch recordings');
      setLoading(false);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchRecordings();
  }, []);

  // Update recordings when stream state changes
  useEffect(() => {
    if (streamState.lastUpdate > lastUpdate) {
      setLastUpdate(streamState.lastUpdate);
      fetchRecordings();
    }
  }, [streamState.lastUpdate]);

  // Poll for updates when stream is active
  useEffect(() => {
    let pollInterval;
    if (streamState.isActive) {
      // Poll every 5 seconds when stream is active
      pollInterval = setInterval(fetchRecordings, 5000);
    }
    return () => {
      if (pollInterval) {
        clearInterval(pollInterval);
      }
    };
  }, [streamState.isActive]);

  const handlePlayRecording = async (recording) => {
    try {
      console.log('Fetching stream for recording:', recording);
      
      const response = await axios.get(
        `${process.env.REACT_APP_API_URL}/recordings/stream/${recording.id}`
      );
      
      console.log('Stream response:', response.data);
      
      const recordingWithStream = {
        ...recording,
        streamUrl: response.data.stream_url,
        format: response.data.format,
        mimeType: response.data.mime_type
      };
      
      console.log('Passing recording to player:', recordingWithStream);
      onSelectRecording(recordingWithStream);
    } catch (err) {
      console.error('Error fetching video stream:', err);
      console.error('Error details:', err.response?.data || err.message);
      setError(`Failed to load video stream: ${err.response?.data?.detail || err.message}`);
    }
  };

  const formatDuration = (duration) => {
    const minutes = Math.floor(duration / 60);
    const seconds = duration % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  if (loading) return (
    <div className="recordings-loading">
      Loading recordings...
    </div>
  );

  if (error) return (
    <div className="recordings-error">
      {error}
    </div>
  );

  return (
    <div className="recordings-container">
      <h2>
        <FaVideo style={{ marginRight: '0.5rem' }} />
        Recorded Streams
      </h2>
      <div className="recordings-list">
        {recordings.length === 0 ? (
          <div className="recordings-empty">
            <FaVideo size={48} style={{ marginBottom: '1rem', opacity: 0.5 }} />
            <p>No recordings available</p>
          </div>
        ) : (
          recordings.map((recording) => (
            <div key={recording.id} className="recording-item">
              <div className="recording-info">
                <h3>{recording.stream_name}</h3>
                <p>
                  <FaCalendarAlt style={{ marginRight: '0.5rem' }} />
                  {new Date(recording.created_at).toLocaleString()}
                </p>
                {recording.duration && (
                  <p>
                    <FaClock style={{ marginRight: '0.5rem' }} />
                    Duration: {formatDuration(recording.duration)}
                  </p>
                )}
              </div>
              <div className="recording-actions">
                <button 
                  onClick={() => handlePlayRecording(recording)}
                  className="view-button"
                >
                  <FaPlay />
                  Play Recording
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default RecordingsList; 