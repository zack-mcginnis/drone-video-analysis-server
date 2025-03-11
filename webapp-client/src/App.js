import React from 'react';
import VideoPlayer from './components/VideoPlayer';
import './App.css';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>DJI Drone Video Stream</h1>
      </header>
      <main>
        <VideoPlayer />
      </main>
      <footer>
        <p>Drone Video Streaming Demo</p>
      </footer>
    </div>
  );
}

export default App; 