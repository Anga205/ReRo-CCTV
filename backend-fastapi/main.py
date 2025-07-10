import asyncio
import threading
import time
from collections import Counter
import cv2
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state with thread safety
active_sockets: dict[WebSocket, int] = {}
frames_needed = Counter()
frames: dict[int, bytes] = {}
lock = threading.Lock()
loop = None  # Event loop reference

# Camera initialization
camera = cv2.VideoCapture(0)
if not camera.isOpened():
    raise RuntimeError("Could not open camera")

async def safe_send(websocket: WebSocket, data: bytes):
    """Safely send data to websocket with error handling"""
    try:
        await websocket.send_bytes(data)
        return True
    except (WebSocketDisconnect, RuntimeError, ConnectionResetError):
        return False

def update_websockets_for_quality(quality: int):
    """Send frame to all websockets requiring this quality"""
    with lock:
        # Get frame and sockets atomically
        frame_data = frames.get(quality, b'')
        sockets = [ws for ws, q in active_sockets.items() if q == quality]
    
    # Send to all sockets in parallel
    async def send_to_all():
        tasks = [safe_send(ws, frame_data) for ws in sockets]
        results = await asyncio.gather(*tasks)
        
        # Remove failed connections
        with lock:
            for i, success in enumerate(results):
                if not success and sockets[i] in active_sockets:
                    q = active_sockets[sockets[i]]
                    frames_needed[q] = max(frames_needed[q] - 1, 0)
                    del active_sockets[sockets[i]]
    
    # Schedule in main event loop
    asyncio.run_coroutine_threadsafe(send_to_all(), loop)

def image_updater():
    """Main camera capture loop running at 34 FPS"""
    last_time = time.perf_counter()
    interval = 1 / 34
    
    while True:
        start_time = time.perf_counter()
        
        # Capture frame
        ret, frame = camera.read()
        if not ret:
            continue
            
        # Get required qualities
        with lock:
            required_qualities = [q for q, count in frames_needed.items() if count > 0]
        
        # Process each required quality
        for quality in required_qualities:
            # Compress image
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            _, buffer = cv2.imencode(".jpg", frame, encode_param)
            compressed = buffer.tobytes()
            
            # Store frame and trigger update
            with lock:
                frames[quality] = compressed
            
            # Start update in background
            threading.Thread(
                target=update_websockets_for_quality,
                args=(quality,),
                daemon=True
            ).start()
        
        # Maintain precise frame rate
        elapsed = time.perf_counter() - start_time
        sleep_time = max(interval - elapsed, 0)
        time.sleep(sleep_time)
        
        # Compensate for processing delays
        next_time = last_time + interval
        while time.perf_counter() < next_time:
            time.sleep(0.001)
        last_time = next_time

@app.websocket("/websocket/{quality}")
async def websocket_endpoint(websocket: WebSocket, quality: int):
    """WebSocket connection handler"""
    # Validate quality
    if quality < 30 or quality > 95:
        await websocket.close(code=1003, reason="Invalid quality parameter")
        return
    
    await websocket.accept()
    
    # Register socket
    with lock:
        active_sockets[websocket] = quality
        frames_needed[quality] += 1
    
    try:
        # Keep connection alive
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        # Clean up on disconnect
        with lock:
            if websocket in active_sockets:
                q = active_sockets[websocket]
                frames_needed[q] = max(frames_needed[q] - 1, 0)
                del active_sockets[websocket]

@app.on_event("startup")
def startup_event():
    """Initialize application"""
    global loop
    loop = asyncio.get_running_loop()
    threading.Thread(target=image_updater, daemon=True).start()

@app.on_event("shutdown")
def shutdown_event():
    """Cleanup resources"""
    camera.release()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=6732)