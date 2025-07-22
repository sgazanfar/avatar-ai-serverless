# src/backend/main.py - Complete integrated backend for Avatar AI System

import asyncio
import json
import base64
import tempfile
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Import our AI services
from avatar_ai_services import avatar_pipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app initialization
app = FastAPI(
    title="Avatar AI System",
    description="Real-time AI Avatar with Speech, Text, and Video Generation",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (for frontend)
if os.path.exists("../frontend"):
    app.mount("/static", StaticFiles(directory="../frontend"), name="static")

class ConnectionManager:
    """WebSocket connection manager for handling multiple users"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_metadata: Dict[str, Dict] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept WebSocket connection and register user"""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_metadata[user_id] = {
            "connected_at": datetime.now().isoformat(),
            "message_count": 0,
            "last_activity": datetime.now().isoformat()
        }
        logger.info(f"User {user_id} connected. Total active: {len(self.active_connections)}")

    def disconnect(self, user_id: str):
        """Remove user connection"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_metadata:
            del self.user_metadata[user_id]
        logger.info(f"User {user_id} disconnected. Total active: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, user_id: str):
        """Send message to specific user"""
        if user_id in self.active_connections:
            try:
                await self.active_connections[user_id].send_text(json.dumps(message))
                self.user_metadata[user_id]["last_activity"] = datetime.now().isoformat()
            except Exception as e:
                logger.error(f"Error sending message to {user_id}: {str(e)}")
                self.disconnect(user_id)

    def get_connection_stats(self) -> dict:
        """Get current connection statistics"""
        return {
            "total_connections": len(self.active_connections),
            "users": list(self.active_connections.keys()),
            "metadata": self.user_metadata
        }

# Global connection manager
manager = ConnectionManager()

@app.get("/")
async def root():
    """Root endpoint - serve the frontend HTML"""
    try:
        return FileResponse("../frontend/index.html")
    except FileNotFoundError:
        return JSONResponse({
            "message": "Avatar AI System API", 
            "status": "running", 
            "timestamp": datetime.now().isoformat(),
            "note": "Frontend not found. API is running normally."
        })

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        health_data = await avatar_pipeline.health_check()
        health_data.update({
            "server_status": "healthy",
            "active_connections": len(manager.active_connections),
            "uptime": "running"
        })
        return health_data
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "server_status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/stats")
async def get_stats():
    """Get system statistics"""
    return {
        "timestamp": datetime.now().isoformat(),
        "connections": manager.get_connection_stats(),
        "system_status": "operational",
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.get("/voices")
async def get_available_voices():
    """Get available TTS voices and avatar types"""
    try:
        return await avatar_pipeline.get_available_voices()
    except Exception as e:
        logger.error(f"Error getting voices: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Failed to get available voices"}
        )

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """Main WebSocket endpoint for real-time communication"""
    await manager.connect(websocket, user_id)
    
    try:
        # Send welcome message
        welcome_message = {
            "type": "system",
            "message": "Connected to Avatar AI! Ready to chat.",
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(welcome_message, user_id)
        
        while True:
            # Receive message from client
            try:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                # Update user activity
                if user_id in manager.user_metadata:
                    manager.user_metadata[user_id]["message_count"] += 1
                    manager.user_metadata[user_id]["last_activity"] = datetime.now().isoformat()
                
                # Process message based on type
                await process_websocket_message(message_data, user_id)
                
            except json.JSONDecodeError:
                error_msg = {
                    "type": "error",
                    "message": "Invalid JSON format",
                    "timestamp": datetime.now().isoformat()
                }
                await manager.send_personal_message(error_msg, user_id)
            except Exception as e:
                logger.error(f"Error processing message from {user_id}: {str(e)}")
                error_msg = {
                    "type": "error", 
                    "message": "Failed to process message",
                    "details": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                await manager.send_personal_message(error_msg, user_id)
                
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        logger.info(f"User {user_id} disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {str(e)}")
        manager.disconnect(user_id)

async def process_websocket_message(message_data: dict, user_id: str):
    """Process incoming WebSocket messages"""
    message_type = message_data.get("type")
    
    if message_type == "text_input":
        await handle_text_input(message_data, user_id)
    elif message_type == "audio_input":
        await handle_audio_input(message_data, user_id)
    elif message_type == "ping":
        # Handle ping/keepalive
        pong_msg = {
            "type": "pong",
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(pong_msg, user_id)
    else:
        error_msg = {
            "type": "error",
            "message": f"Unknown message type: {message_type}",
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(error_msg, user_id)

async def handle_text_input(message_data: dict, user_id: str):
    """Handle text input messages"""
    try:
        text = message_data.get("text", "").strip()
        avatar_type = message_data.get("avatar_type", "female")
        voice = message_data.get("voice", "alloy")
        
        if not text:
            error_msg = {
                "type": "error",
                "message": "Empty text input",
                "timestamp": datetime.now().isoformat()
            }
            await manager.send_personal_message(error_msg, user_id)
            return
        
        logger.info(f"Processing text input from {user_id}: {text[:50]}...")
        
        # Send processing status
        processing_msg = {
            "type": "processing",
            "message": "AI is generating response...",
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(processing_msg, user_id)
        
        # Process through AI pipeline
        result = await avatar_pipeline.process_text_input(text, user_id, avatar_type, voice)
        
        if result.get("status") == "success":
            response_msg = {
                "type": "text_response",
                "user_input": result["user_input"],
                "text": result["ai_response_text"],
                "avatar_video_url": result["avatar_video_url"],
                "tokens_used": result.get("tokens_used", 0),
                "processing_time": result["processing_time"],
                "timestamp": datetime.now().isoformat()
            }
        else:
            response_msg = {
                "type": "error",
                "message": result.get("error", "Processing failed"),
                "timestamp": datetime.now().isoformat()
            }
        
        await manager.send_personal_message(response_msg, user_id)
        
    except Exception as e:
        logger.error(f"Error handling text input for {user_id}: {str(e)}")
        error_msg = {
            "type": "error",
            "message": "Failed to process text input",
            "details": str(e),
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(error_msg, user_id)

async def handle_audio_input(message_data: dict, user_id: str):
    """Handle audio input messages"""
    try:
        audio_data_b64 = message_data.get("audio_data")
        avatar_type = message_data.get("avatar_type", "female")
        voice = message_data.get("voice", "alloy")
        
        if not audio_data_b64:
            error_msg = {
                "type": "error",
                "message": "No audio data provided",
                "timestamp": datetime.now().isoformat()
            }
            await manager.send_personal_message(error_msg, user_id)
            return
        
        logger.info(f"Processing audio input from {user_id}")
        
        # Send processing status
        processing_msg = {
            "type": "processing",
            "message": "Processing voice input...",
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(processing_msg, user_id)
        
        # Decode base64 audio
        try:
            audio_bytes = base64.b64decode(audio_data_b64)
        except Exception as e:
            error_msg = {
                "type": "error",
                "message": "Invalid audio data format",
                "timestamp": datetime.now().isoformat()
            }
            await manager.send_personal_message(error_msg, user_id)
            return
        
        # Process through AI pipeline
        result = await avatar_pipeline.process_audio_input(audio_bytes, user_id, avatar_type, voice)
        
        if result.get("status") == "success":
            response_msg = {
                "type": "audio_response",
                "transcribed_text": result["transcribed_text"],
                "llm_response": result["ai_response_text"],
                "avatar_video_url": result["avatar_video_url"],
                "tokens_used": result.get("tokens_used", 0),
                "processing_time": result["processing_time"],
                "timestamp": datetime.now().isoformat()
            }
        else:
            response_msg = {
                "type": "error",
                "message": result.get("error", "Audio processing failed"),
                "timestamp": datetime.now().isoformat()
            }
        
        await manager.send_personal_message(response_msg, user_id)
        
    except Exception as e:
        logger.error(f"Error handling audio input for {user_id}: {str(e)}")
        error_msg = {
            "type": "error",
            "message": "Failed to process audio input",
            "details": str(e),
            "timestamp": datetime.now().isoformat()
        }
        await manager.send_personal_message(error_msg, user_id)

# Additional API endpoints for management and testing

@app.post("/api/test-text")
async def test_text_processing(request: dict):
    """Test endpoint for text processing"""
    try:
        text = request.get("text", "Hello, how are you?")
        user_id = request.get("user_id", "test_user")
        avatar_type = request.get("avatar_type", "female")
        voice = request.get("voice", "alloy")
        
        result = await avatar_pipeline.process_text_input(text, user_id, avatar_type, voice)
        return result
    except Exception as e:
        logger.error(f"Test endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/status")
async def get_user_status(user_id: str):
    """Get specific user connection status"""
    if user_id in manager.user_metadata:
        return {
            "user_id": user_id,
            "connected": True,
            "metadata": manager.user_metadata[user_id]
        }
    else:
        return {
            "user_id": user_id,
            "connected": False
        }

@app.delete("/api/user/{user_id}/disconnect")
async def force_disconnect_user(user_id: str):
    """Force disconnect a specific user"""
    if user_id in manager.active_connections:
        try:
            await manager.active_connections[user_id].close()
            manager.disconnect(user_id)
            return {"message": f"User {user_id} disconnected"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=404, detail="User not found")

@app.get("/api/system/info")
async def get_system_info():
    """Get system information"""
    return {
        "system": "Avatar AI System",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "timestamp": datetime.now().isoformat(),
        "active_connections": len(manager.active_connections),
        "features": {
            "speech_to_text": True,
            "text_to_speech": True,
            "avatar_generation": True,
            "real_time_chat": True,
            "azure_integration": bool(os.getenv("AZURE_STORAGE_ACCOUNT"))
        }
    }

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Application startup tasks"""
    logger.info("Avatar AI System starting up...")
    
    # Verify environment variables
    required_env_vars = ["OPENAI_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        # Don't raise exception in production, just log warning
        logger.warning("Some features may not work properly without required environment variables")
    
    # Test AI services
    try:
        health = await avatar_pipeline.health_check()
        logger.info(f"AI services health check: {health}")
    except Exception as e:
        logger.warning(f"AI services health check failed: {str(e)}")
    
    logger.info("Avatar AI System started successfully!")

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks"""
    logger.info("Avatar AI System shutting down...")
    
    # Close all WebSocket connections
    for user_id in list(manager.active_connections.keys()):
        try:
            await manager.active_connections[user_id].close()
        except Exception:
            pass
        manager.disconnect(user_id)
    
    logger.info("Avatar AI System shutdown complete!")

# Error handlers
@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    logger.error(f"Internal server error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error", 
            "message": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found", 
            "message": "The requested resource was not found",
            "timestamp": datetime.now().isoformat()
        }
    )

# Main application runner
if __name__ == "__main__":
    # Load environment variables from .env file if it exists
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info("Environment variables loaded from .env file")
    except ImportError:
        logger.warning("python-dotenv not installed, skipping .env file loading")
    
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "False").lower() == "true"
    workers = int(os.getenv("WORKERS", 1))
    
    logger.info(f"Starting Avatar AI System on {host}:{port}")
    
    if debug:
        # Development mode - single worker with reload
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=True,
            log_level="info"
        )
    else:
        # Production mode
        uvicorn.run(
            app,
            host=host,
            port=port,
            workers=workers,
            log_level="info",
            access_log=True
        )
