import React, { useState, useEffect, useRef } from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:6732";

const LiveStream: React.FC = () => {
  const [currentQuality, setCurrentQuality] = useState<number>(95);
  const [currentFps, setCurrentFps] = useState<number>(30);
  const [connectionStatus, setConnectionStatus] = useState<string>("Connecting...");
  
  const wsRef = useRef<WebSocket | null>(null);
  const frameTimesRef = useRef<number[]>([]);
  const fpsIntervalRef = useRef<number | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const currentQualityRef = useRef<number>(95);

  // Update FPS calculation
  const updateFps = () => {
    const now = Date.now();
    const fiveSecondsAgo = now - 5000;
    frameTimesRef.current = frameTimesRef.current.filter(t => t > fiveSecondsAgo);
    setCurrentFps(frameTimesRef.current.length / 5);
  };

  // Handle quality adjustment
  const adjustQuality = () => {
    const quality = currentQualityRef.current;
    if (currentFps < 28 && quality > 30) {
      const newQuality = Math.max(quality - 5, 30);
      setConnectionStatus(`Adjusting quality to ${newQuality} (low FPS)`);
      reconnect(newQuality);
    } else if (currentFps > 32 && quality < 95) {
      const newQuality = Math.min(quality + 5, 95);
      setConnectionStatus(`Adjusting quality to ${newQuality} (high FPS)`);
      reconnect(newQuality);
    }
  };

  // Reconnect with new quality
  const reconnect = (quality: number) => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    connectWebSocket(quality);
  };

  // Establish WebSocket connection
  const connectWebSocket = (quality: number) => {
    setConnectionStatus(`Connecting to quality ${quality}...`);
    setCurrentQuality(quality);
    currentQualityRef.current = quality;
    
    const ws = new WebSocket(`${BACKEND_URL}/websocket/${quality}`);
    ws.binaryType = "arraybuffer";
    
    ws.onopen = () => {
      setConnectionStatus("Connected");
      frameTimesRef.current = [];
    };
    
    ws.onmessage = (event) => {
      const timestamp = Date.now();
      frameTimesRef.current.push(timestamp);
      
      // Update image display
      if (imgRef.current) {
        const blob = new Blob([event.data], { type: "image/jpeg" });
        const newUrl = URL.createObjectURL(blob);
        
        // Revoke previous URL to prevent memory leaks
        if (imgRef.current.src) URL.revokeObjectURL(imgRef.current.src);
        imgRef.current.src = newUrl;
      }
    };
    
    ws.onerror = () => {
      setConnectionStatus("Connection error");
    };
    
    ws.onclose = () => {
      setConnectionStatus("Disconnected");
    };
    
    wsRef.current = ws;
  };

  // Initial connection and cleanup
  useEffect(() => {
    connectWebSocket(95);
    
    // Setup FPS monitoring
    fpsIntervalRef.current = window.setInterval(() => {
      updateFps();
      adjustQuality();
    }, 1000);
    
    return () => {
      if (fpsIntervalRef.current) clearInterval(fpsIntervalRef.current);
      if (wsRef.current) wsRef.current.close();
      if (imgRef.current?.src) URL.revokeObjectURL(imgRef.current.src);
    };
  }, []);

  return (
    <div className="max-h-full max-w-full">
      <div className="stats bg-gray-800 text-white p-4 rounded shadow-md">
        <span className="block mb-2">Quality: <span className="font-semibold">{currentQuality}%</span></span>
        <span className="block mb-2">FPS: <span className="font-semibold">{currentFps.toFixed(2)}</span></span>
        <span className="block">Status: <span className={`font-semibold ${connectionStatus === 'Connected' ? 'text-green-500' : 'text-red-500'}`}>{connectionStatus}</span></span>
      </div>
      <img 
        ref={imgRef} 
        alt="Live Stream" 
        className="h-[75vh]"
      />
    </div>
  );
};

export default LiveStream;