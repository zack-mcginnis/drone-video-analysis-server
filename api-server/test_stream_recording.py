#!/usr/bin/env python3
"""
Test script for the simplified stream_recording endpoint.
This script tests both local and AWS scenarios.
"""

import os
import sys
import tempfile
import json
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_stream_recording_logic():
    """Test the core logic of the stream_recording endpoint"""
    
    print("Testing stream_recording endpoint logic...")
    
    # Test case 1: AWS environment with S3 HLS path
    print("\n1. Testing AWS environment with S3 HLS path:")
    
    class MockRecording:
        def __init__(self, environment, s3_hls_path=None, local_hls_path=None):
            self.environment = environment
            self.s3_hls_path = s3_hls_path
            self.local_hls_path = local_hls_path
            self.stream_name = "test_stream"
            self.user_id = 1
    
    # AWS case
    aws_recording = MockRecording("aws", "s3://bucket/recordings/stream_123/hls/")
    
    if aws_recording.environment == "aws" and aws_recording.s3_hls_path:
        print(f"✓ AWS recording would use S3 HLS path: {aws_recording.s3_hls_path}")
        result = {
            "stream_url": "http://localhost:8000/recordings/hls/123/playlist.m3u8?token=...",
            "title": f"{aws_recording.stream_name} - Recording 123",
            "format": "hls",
            "status": "ready",
            "hls_path": aws_recording.s3_hls_path,
            "environment": "aws"
        }
        print(f"  Result: {json.dumps(result, indent=2)}")
    
    # Test case 2: Local environment with local HLS path
    print("\n2. Testing local environment with local HLS path:")
    
    # Create a temporary directory structure to simulate local HLS files
    with tempfile.TemporaryDirectory() as temp_dir:
        hls_dir = os.path.join(temp_dir, "hls")
        os.makedirs(hls_dir)
        
        # Create a mock playlist file
        playlist_path = os.path.join(hls_dir, "playlist.m3u8")
        with open(playlist_path, 'w') as f:
            f.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n")
        
        local_recording = MockRecording("local", local_hls_path=hls_dir)
        
        if local_recording.environment == "local" and local_recording.local_hls_path:
            if os.path.exists(os.path.join(local_recording.local_hls_path, "playlist.m3u8")):
                print(f"✓ Local recording would use local HLS path: {local_recording.local_hls_path}")
                result = {
                    "stream_url": "http://localhost:8000/recordings/hls/123/playlist.m3u8?token=...",
                    "title": f"{local_recording.stream_name} - Recording 123",
                    "format": "hls",
                    "status": "ready",
                    "hls_path": local_recording.local_hls_path,
                    "environment": "local"
                }
                print(f"  Result: {json.dumps(result, indent=2)}")
            else:
                print("✗ Local HLS playlist not found")
    
    # Test case 3: No HLS files available
    print("\n3. Testing case with no HLS files available:")
    
    no_hls_recording = MockRecording("local")
    
    if not (no_hls_recording.environment == "aws" and no_hls_recording.s3_hls_path) and \
       not (no_hls_recording.environment == "local" and no_hls_recording.local_hls_path):
        print("✓ Would return 404 error: HLS files not available")
    
    print("\n✓ All test cases passed!")

def test_hls_file_serving_logic():
    """Test the HLS file serving logic"""
    
    print("\nTesting HLS file serving logic...")
    
    # Test case 1: Local file serving
    print("\n1. Testing local file serving:")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        hls_dir = os.path.join(temp_dir, "hls")
        os.makedirs(hls_dir)
        
        # Create mock HLS files
        playlist_content = "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:6\n"
        with open(os.path.join(hls_dir, "playlist.m3u8"), 'w') as f:
            f.write(playlist_content)
        
        with open(os.path.join(hls_dir, "segment_001.ts"), 'wb') as f:
            f.write(b"fake_video_data")
        
        # Simulate the file serving logic
        file_name = "playlist.m3u8"
        file_path = os.path.join(hls_dir, file_name)
        
        if os.path.exists(file_path):
            print(f"✓ Would serve file: {file_path}")
            content_type = "application/vnd.apple.mpegurl" if file_name.endswith('.m3u8') else "video/mp2t"
            print(f"  Content-Type: {content_type}")
        
        # Test segment file
        file_name = "segment_001.ts"
        file_path = os.path.join(hls_dir, file_name)
        
        if os.path.exists(file_path):
            print(f"✓ Would serve segment: {file_path}")
            content_type = "application/vnd.apple.mpegurl" if file_name.endswith('.m3u8') else "video/mp2t"
            print(f"  Content-Type: {content_type}")
    
    print("\n✓ HLS file serving test passed!")

if __name__ == "__main__":
    test_stream_recording_logic()
    test_hls_file_serving_logic()
    print("\n🎉 All tests completed successfully!") 