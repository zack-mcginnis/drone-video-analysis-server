import React, { useState, useEffect } from 'react';
import VideoPlayer from './components/VideoPlayer';
import RecordingsList from './components/RecordingsList';
import './App.css';

function App() {
  const [selectedRecording, setSelectedRecording] = useState(null);
  const [isLiveMode, setIsLiveMode] = useState(true);
  const [streamState, setStreamState] = useState({
    isActive: false,
    lastUpdate: Date.now()
  });

  const handleRecordingSelect = (recording) => {
    setSelectedRecording(recording);
    setIsLiveMode(false);
    // Update stream state when selecting a recording
    setStreamState(prev => ({
      ...prev,
      lastUpdate: Date.now()
    }));
  };

  const handleSwitchToLive = () => {
    setSelectedRecording(null);
    setIsLiveMode(true);
    // Update stream state when switching to live
    setStreamState(prev => ({
      ...prev,
      lastUpdate: Date.now()
    }));
  };

  const handleStreamStateChange = (isActive) => {
    setStreamState(prev => ({
      isActive,
      lastUpdate: Date.now()
    }));
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>DJI Drone Video Stream</h1>
      </header>
      <main>
        <VideoPlayer 
          isLiveMode={isLiveMode}
          selectedRecording={selectedRecording}
          onSwitchToLive={handleSwitchToLive}
          onStreamStateChange={handleStreamStateChange}
        />
        <RecordingsList 
          onSelectRecording={handleRecordingSelect}
          streamState={streamState}
        />
      </main>
      <footer>
        <p>Drone Video Streaming Demo</p>
      </footer>
    </div>
  );
}

export default App; 