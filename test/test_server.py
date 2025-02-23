import requests
import time
import subprocess
import sys
import os

def check_nginx_status():
    """Check if NGINX server is running"""
    nginx_status_url = os.getenv('NGINX_STATUS_URL', 'http://rtmp-server:8080/status')
    max_retries = 30
    retry_delay = 1

    print(f"Checking NGINX status at: {nginx_status_url}")
    
    for i in range(max_retries):
        try:
            response = requests.get(nginx_status_url)
            if response.status_code == 200:
                print("NGINX server is ready")
                return True
        except requests.exceptions.RequestException:
            pass
        
        print(f"Waiting for NGINX server... ({i+1}/{max_retries})")
        time.sleep(retry_delay)
    
    return False

def run_tests():
    """Run the test suite"""
    print("Starting RTMP server tests...")

    # Check if NGINX is running
    if not check_nginx_status():
        print("Error: NGINX server is not running or not ready")
        return False

    # Start streaming mock data
    print("\nStarting mock stream...")
    rtmp_url = os.getenv('RTMP_URL', 'rtmp://rtmp-server:1935/live/stream')
    
    stream_process = subprocess.Popen(
        [sys.executable, 'send_mock_stream.py'],
        env=dict(os.environ, RTMP_URL=rtmp_url),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for a few seconds to let the stream initialize
    time.sleep(5)

    # Check if the stream process is still running
    if stream_process.poll() is not None:
        print("Error: Stream process failed to start")
        stderr = stream_process.stderr.read().decode()
        print(f"Stream process error: {stderr}")
        return False

    print("Mock stream is running")

    # Let the stream run for a few seconds
    print("\nStreaming test data for 10 seconds...")
    time.sleep(10)

    # Clean up
    stream_process.terminate()
    stream_process.wait()

    print("\nTests completed successfully!")
    return True

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1) 