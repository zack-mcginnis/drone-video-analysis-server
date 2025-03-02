import asyncio
import websockets
import cv2
import numpy as np
from aiohttp import web
import subprocess as sp
import json
import sys
import logging
import time
import re

# Configure logging to be more verbose and immediate
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout  # Explicitly use stdout
)

class StreamServer:
    def __init__(self):
        logging.info("Initializing StreamServer")
        self.clients = set()
        self.rtmp_url = 'rtmp://0.0.0.0:1935/live/stream'
        self.frame_buffer = None
        self.is_streaming = False

    async def start_rtmp_reader(self):
        logging.info("Starting RTMP reader")
        """Read frames from RTMP stream"""
        
        # Higher default resolution - we'll try to detect actual resolution
        width, height = 1920, 1080
        
        while True:
            try:
                logging.info(f"Connecting to RTMP stream at {self.rtmp_url}")
                
                # First, check if the stream is available and get its resolution
                probe_command = [
                    'ffprobe',
                    '-i', self.rtmp_url,
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height',
                    '-of', 'json',
                    '-fflags', '+igndts',  # Ignore DTS timestamps
                ]
                
                # Start probe process
                probe_process = await asyncio.create_subprocess_exec(
                    *probe_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                logging.info("Checking if stream is available and detecting resolution...")
                stream_available = False
                
                # Wait for probe process to complete
                stdout_data, stderr_data = await probe_process.communicate()
                
                # Check if we got stream info
                if probe_process.returncode == 0:
                    try:
                        # Parse the JSON output
                        probe_output = json.loads(stdout_data.decode())
                        if 'streams' in probe_output and probe_output['streams']:
                            stream = probe_output['streams'][0]
                            if 'width' in stream and 'height' in stream:
                                width = stream['width']
                                height = stream['height']
                                logging.info(f"Detected stream resolution: {width}x{height}")
                                stream_available = True
                    except Exception as e:
                        logging.error(f"Error parsing probe output: {e}")
                
                # Check stderr for stream info if we couldn't get it from stdout
                if not stream_available:
                    stderr_text = stderr_data.decode()
                    for line in stderr_text.splitlines():
                        logging.info(f"Probe: {line}")
                        if "Stream #" in line:
                            stream_available = True
                            # Try to extract resolution from the stream info line
                            match = re.search(r'(\d+)x(\d+)', line)
                            if match:
                                width = int(match.group(1))
                                height = int(match.group(2))
                                logging.info(f"Detected stream resolution from stderr: {width}x{height}")
                            break
                
                if not stream_available:
                    logging.warning("No stream available, waiting before retry...")
                    await asyncio.sleep(5)
                    continue
                
                # Now that we know the stream is available, start reading frames
                # Use FFmpeg to convert RTMP to JPEG images via pipe with high quality
                command = [
                    'ffmpeg',
                    '-i', self.rtmp_url,
                    '-an',                      # Disable audio
                    '-sn',                      # Disable subtitles
                    '-f', 'image2pipe',         # Output to pipe
                    '-c:v', 'mjpeg',            # JPEG codec
                    '-q:v', '1',                # Highest JPEG quality (1-31, lower is better)
                    '-loglevel', 'info',        # Show connection info
                    '-fflags', '+igndts',       # Ignore DTS timestamps
                    '-vsync', 'passthrough',    # Maintain original timestamps
                    '-r', '60',                 # 60 fps
                    'pipe:1'                    # Output to stdout
                ]
                
                # Start FFmpeg process
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                logging.info(f"FFmpeg process started, reading high-resolution frames ({width}x{height})...")
                self.is_streaming = True
                frame_count = 0
                last_log_time = time.time()
                
                # Start stderr monitor
                stderr_monitor = asyncio.create_task(self._monitor_stderr(process.stderr))
                
                # JPEG start/end markers
                jpeg_start = b'\xff\xd8'
                jpeg_end = b'\xff\xd9'
                
                # Buffer for collecting JPEG data
                buffer = bytearray()
                
                # Read JPEG frames from pipe
                while True:
                    # Read a chunk of data
                    chunk = await process.stdout.read(8192)  # Increased chunk size for higher resolution
                    if not chunk:
                        logging.warning("End of FFmpeg output stream")
                        break
                    
                    # Add chunk to buffer
                    buffer.extend(chunk)
                    
                    # Process all complete JPEG images in buffer
                    while True:
                        # Find start of JPEG
                        start_idx = buffer.find(jpeg_start)
                        if start_idx == -1:
                            break  # No start marker found
                        
                        # Find end of JPEG
                        end_idx = buffer.find(jpeg_end, start_idx)
                        if end_idx == -1:
                            break  # No end marker found
                        
                        # Extract complete JPEG (including end marker)
                        end_idx += 2
                        jpeg_data = buffer[start_idx:end_idx]
                        
                        # Remove processed JPEG from buffer
                        buffer = buffer[end_idx:]
                        
                        # Process the JPEG frame
                        try:
                            # Decode JPEG to numpy array
                            frame = cv2.imdecode(np.frombuffer(jpeg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if frame is None:
                                logging.warning("Failed to decode JPEG frame")
                                continue
                            
                            # Store frame in buffer for HTTP streaming
                            self.frame_buffer = frame
                            
                            # Count frames for logging
                            frame_count += 1
                            current_time = time.time()
                            if current_time - last_log_time >= 5:  # Log every 5 seconds
                                fps = frame_count / (current_time - last_log_time)
                                logging.info(f"Receiving frames at {fps:.2f} FPS ({width}x{height})")
                                frame_count = 0
                                last_log_time = current_time
                            
                            # Send frame to all connected WebSocket clients
                            if self.clients:
                                # For WebSocket, we might want to resize for bandwidth efficiency
                                # Only resize if the frame is very large
                                if width > 1280 and len(self.clients) > 3:  # More than 3 clients
                                    # Resize for WebSocket to reduce bandwidth
                                    scale_factor = 1280 / width
                                    ws_width = 1280
                                    ws_height = int(height * scale_factor)
                                    ws_frame = cv2.resize(frame, (ws_width, ws_height))
                                    _, ws_jpeg = cv2.imencode('.jpg', ws_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                                    await self.broadcast(ws_jpeg.tobytes())
                                else:
                                    # Use original high-quality JPEG data
                                    await self.broadcast(jpeg_data)
                                
                        except Exception as e:
                            logging.error(f"Error processing frame: {e}")
                    
                    # Check if process is still running
                    if process.returncode is not None:
                        logging.error(f"FFmpeg process exited with code {process.returncode}")
                        break
                
                # If we get here, the stream has ended or there was an error
                self.is_streaming = False
                logging.info("Stream ended or disconnected")
                
                # Cancel stderr monitor task
                if not stderr_monitor.done():
                    stderr_monitor.cancel()
                
                # Clean up process
                try:
                    process.kill()
                except:
                    pass
                    
                # Wait before reconnecting
                logging.info("Waiting 5 seconds before reconnecting...")
                await asyncio.sleep(5)
                
            except Exception as e:
                self.is_streaming = False
                logging.error(f"Error in RTMP reader: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _read_frame_with_progress(self, stream, size):
        """Read a frame with progress updates to avoid appearing hung"""
        buffer = bytearray()
        bytes_read = 0
        last_progress_log = time.time()
        
        while bytes_read < size:
            # Read in smaller chunks to avoid blocking for too long
            chunk = await stream.read(min(4096, size - bytes_read))
            
            if not chunk:  # EOF
                return bytes(buffer)
            
            buffer.extend(chunk)
            bytes_read += len(chunk)
            
            # Log progress occasionally
            if time.time() - last_progress_log > 2:
                logging.info(f"Reading frame: {bytes_read}/{size} bytes ({bytes_read/size*100:.1f}%)")
                last_progress_log = time.time()
        
        return bytes(buffer)

    async def _monitor_stderr(self, stderr):
        """Monitor FFmpeg stderr for connection status and errors"""
        while True:
            line = await stderr.readline()
            if not line:
                break
            
            line_text = line.decode().strip()
            
            # Log important messages
            if any(keyword in line_text for keyword in ["Connection", "Stream", "Error", "error", "failed"]):
                logging.info(f"FFmpeg: {line_text}")

    async def websocket_handler(self, websocket):
        logging.info("New WebSocket connection")
        """Handle WebSocket connections"""
        try:
            self.clients.add(websocket)
            logging.info(f"Client connected. Total clients: {len(self.clients)}")
            
            while True:
                # Keep connection alive and handle client messages
                message = await websocket.recv()
                try:
                    data = json.loads(message)
                    if data.get('type') == 'ping':
                        await websocket.send(json.dumps({'type': 'pong'}))
                except:
                    pass

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.remove(websocket)
            logging.info(f"Client disconnected. Total clients: {len(self.clients)}")

    async def broadcast(self, frame_data):
        """Send frame to all connected clients"""
        if not self.clients:
            return

        # Create tasks for each client
        tasks = []
        for client in self.clients:
            try:
                message = json.dumps({
                    'type': 'frame',
                    'data': frame_data.hex()  # Convert bytes to hex string
                })
                tasks.append(asyncio.create_task(client.send(message)))
            except:
                pass
        
        # Wait for all sends to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def http_handler(self, request):
        """Handle HTTP requests for video stream"""
        if not self.is_streaming or self.frame_buffer is None:
            return web.Response(text="No active stream", status=503)
        
        # Set response headers for multipart stream
        response = web.StreamResponse(
            status=200,
            reason='OK',
            headers={
                'Content-Type': 'multipart/x-mixed-replace;boundary=frame',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Connection': 'close',
            }
        )
        
        await response.prepare(request)
        
        try:
            while True:
                if not self.is_streaming or self.frame_buffer is None:
                    break
                    
                # Get the current frame
                frame = self.frame_buffer
                
                # Encode frame as JPEG with high quality
                _, jpeg_data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                jpeg_bytes = jpeg_data.tobytes()
                
                # Send frame as multipart response
                await response.write(
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    b'Content-Length: ' + str(len(jpeg_bytes)).encode() + b'\r\n'
                    b'\r\n' + jpeg_bytes + b'\r\n'
                )
                
                # Control frame rate to avoid overwhelming the client
                await asyncio.sleep(1/60)  # 60 FPS max
                
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        finally:
            return response

    async def start_server(self):
        logging.info("Starting server")
        """Start both WebSocket and HTTP servers"""
        # Create aiohttp app for HTTP streaming
        app = web.Application()
        
        # Add CORS middleware
        async def cors_middleware(app, handler):
            async def middleware_handler(request):
                if request.method == 'OPTIONS':
                    # Handle CORS preflight requests
                    headers = {
                        'Access-Control-Allow-Origin': 'http://localhost:3000',
                        'Access-Control-Allow-Methods': 'GET, OPTIONS',
                        'Access-Control-Allow-Headers': '*',
                        'Access-Control-Allow-Credentials': 'true',
                        'Access-Control-Max-Age': '1728000',
                    }
                    return web.Response(headers=headers)
                
                # Add CORS headers to the response
                response = await handler(request)
                response.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                return response
            return middleware_handler

        app.middlewares.append(cors_middleware)
        app.router.add_get('/stream', self.http_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8082)
        await site.start()

        # Start WebSocket server on port 8083 with CORS origins
        async with websockets.serve(
            self.websocket_handler, 
            '0.0.0.0', 
            8083,
            origins=['http://localhost:3000']
        ):
            # Start RTMP reader
            await self.start_rtmp_reader()

if __name__ == '__main__':
    try:
        server = StreamServer()
        asyncio.run(server.start_server())
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)