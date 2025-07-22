# src/backend/avatar_ai_services.py - Core AI services optimized for serverless Azure deployment

import asyncio
import httpx
import openai
import base64
import json
import os
from typing import Optional, Dict, Any
import tempfile
import wave
import io
from datetime import datetime
import logging
from azure.storage.blob import BlobServiceClient
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient
import redis.asyncio as redis
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AzureStorageService:
    """Azure Blob Storage service for caching and content delivery"""
    
    def __init__(self):
        self.account_name = os.getenv("AZURE_STORAGE_ACCOUNT")
        self.account_key = os.getenv("AZURE_STORAGE_KEY")
        self.cdn_endpoint = os.getenv("CDN_ENDPOINT_URL", "")
        
        # Initialize blob service client
        if self.account_name and self.account_key:
            try:
                self.blob_service = AsyncBlobServiceClient(
                    account_url=f"https://{self.account_name}.blob.core.windows.net",
                    credential=self.account_key
                )
                logger.info("Azure Storage service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Azure Storage: {e}")
                self.blob_service = None
        else:
            logger.warning("Azure Storage credentials not configured")
            self.blob_service = None
    
    async def upload_avatar_video(self, video_data: bytes, user_id: str, video_id: str) -> str:
        """Upload avatar video to blob storage and return CDN URL"""
        try:
            if not self.blob_service:
                raise Exception("Azure Storage not configured")
                
            blob_name = f"avatars/{user_id}/{video_id}.mp4"
            
            # Upload to blob storage
            blob_client = self.blob_service.get_blob_client(
                container="avatar-videos", 
                blob=blob_name
            )
            
            await blob_client.upload_blob(
                video_data, 
                overwrite=True,
                content_settings={"content_type": "video/mp4"}
            )
            
            # Return CDN URL if available, otherwise blob URL
            if self.cdn_endpoint:
                return f"{self.cdn_endpoint}/avatar-videos/{blob_name}"
            else:
                return f"https://{self.account_name}.blob.core.windows.net/avatar-videos/{blob_name}"
                
        except Exception as e:
            logger.error(f"Error uploading avatar video: {str(e)}")
            raise
    
    async def cache_audio(self, audio_data: bytes, cache_key: str) -> str:
        """Cache audio data in blob storage"""
        try:
            if not self.blob_service:
                return None
                
            blob_name = f"audio/{cache_key}.wav"
            blob_client = self.blob_service.get_blob_client(
                container="audio-cache", 
                blob=blob_name
            )
            
            await blob_client.upload_blob(
                audio_data, 
                overwrite=True,
                content_settings={"content_type": "audio/wav"}
            )
            
            return blob_name
            
        except Exception as e:
            logger.error(f"Error caching audio: {str(e)}")
            return None

class RedisQueueService:
    """Redis queue service for managing processing tasks"""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL")
        self.redis_client = None
        
    async def connect(self):
        """Connect to Redis"""
        if self.redis_url and not self.redis_client:
            try:
                self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
                await self.redis_client.ping()
                logger.info("Redis connection established successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.redis_client = None
        else:
            logger.warning("Redis URL not configured")
    
    async def add_processing_task(self, task_data: dict) -> str:
        """Add task to processing queue"""
        try:
            if not self.redis_client:
                await self.connect()
                
            if not self.redis_client:
                raise Exception("Redis not available")
                
            task_id = f"task_{datetime.now().timestamp()}_{hash(str(task_data))}"
            task_data["task_id"] = task_id
            
            await self.redis_client.lpush(
                "avatar_processing_queue", 
                json.dumps(task_data)
            )
            
            logger.info(f"Task {task_id} added to processing queue")
            return task_id
            
        except Exception as e:
            logger.error(f"Error adding task to queue: {str(e)}")
            raise
    
    async def get_task_result(self, task_id: str, timeout: int = 60) -> dict:
        """Wait for task result"""
        try:
            if not self.redis_client:
                await self.connect()
                
            if not self.redis_client:
                raise Exception("Redis not available")
                
            result_key = f"task_result:{task_id}"
            
            # Wait for result with timeout
            for i in range(timeout):
                result = await self.redis_client.get(result_key)
                if result:
                    await self.redis_client.delete(result_key)  # Clean up
                    return json.loads(result)
                await asyncio.sleep(1)
                
            raise Exception("Task timeout")
            
        except Exception as e:
            logger.error(f"Error getting task result: {str(e)}")
            raise

class STTService:
    """Speech-to-Text service using OpenAI Whisper"""
    
    def __init__(self):
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise Exception("OPENAI_API_KEY environment variable not set")
        self.client = openai.OpenAI(api_key=openai_key)
    
    async def transcribe_audio(self, audio_data: bytes, format: str = "webm") -> str:
        """Transcribe audio to text using Whisper"""
        try:
            # Create temporary file for audio
            with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            # Transcribe using Whisper
            with open(temp_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="en"  # Can be made dynamic
                )
            
            # Clean up temp file
            os.unlink(temp_file_path)
            
            logger.info(f"Successfully transcribed audio: {transcript.text[:50]}...")
            return transcript.text
            
        except Exception as e:
            logger.error(f"STT Error: {str(e)}")
            raise Exception(f"Speech recognition failed: {str(e)}")

class LLMService:
    """Large Language Model service using OpenAI GPT"""
    
    def __init__(self):
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise Exception("OPENAI_API_KEY environment variable not set")
        self.client = openai.OpenAI(api_key=openai_key)
        self.model = "gpt-4o-mini"  # Cost-optimized model for production
        
        # System prompt optimized for avatar conversations
        self.system_prompt = """You are a friendly, helpful AI avatar assistant. 
        You speak naturally and conversationally, as if you're a real person having a face-to-face conversation.
        Keep responses concise but engaging (1-3 sentences typically, maximum 150 words).
        Be expressive and use natural speech patterns that will work well with lip-sync technology.
        Avoid using markdown, bullet points, or structured text - speak naturally as if talking to someone.
        Show personality and emotion in your responses while remaining helpful and professional.
        Use contractions and casual language to sound more human and natural."""
    
    async def generate_response(self, user_input: str, user_id: str, conversation_history: list = None) -> Dict[str, Any]:
        """Generate AI response using GPT"""
        try:
            # Prepare conversation history
            messages = [{"role": "system", "content": self.system_prompt}]
            
            if conversation_history:
                messages.extend(conversation_history[-10:])  # Keep last 10 messages for context
            
            messages.append({"role": "user", "content": user_input})
            
            # Generate response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=150,  # Keep responses concise for avatar
                temperature=0.8,  # Slightly creative but consistent
                stream=False
            )
            
            ai_response = response.choices[0].message.content
            
            logger.info(f"Generated AI response for user {user_id}: {ai_response[:50]}...")
            
            return {
                "text": ai_response,
                "model": self.model,
                "tokens_used": response.usage.total_tokens,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"LLM Error: {str(e)}")
            raise Exception(f"AI response generation failed: {str(e)}")

class TTSService:
    """Text-to-Speech service using OpenAI TTS"""
    
    def __init__(self):
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise Exception("OPENAI_API_KEY environment variable not set")
        self.client = openai.OpenAI(api_key=openai_key)
        self.storage_service = AzureStorageService()
    
    async def synthesize_speech(self, text: str, voice: str = "alloy", user_id: str = None) -> bytes:
        """Convert text to speech using OpenAI TTS"""
        try:
            # Clean text for TTS
            clean_text = text.strip()
            if len(clean_text) > 4000:  # OpenAI TTS limit
                clean_text = clean_text[:4000] + "..."
            
            response = self.client.audio.speech.create(
                model="tts-1-hd",  # High quality model
                voice=voice,  # alloy, echo, fable, onyx, nova, shimmer
                input=clean_text,
                response_format="wav"
            )
            
            logger.info(f"Generated TTS audio for text: {clean_text[:50]}...")
            return response.content
            
        except Exception as e:
            logger.error(f"TTS Error: {str(e)}")
            raise Exception(f"Speech synthesis failed: {str(e)}")

class DIDService:
    """D-ID service for realistic talking avatar generation with Azure integration"""
    
    def __init__(self):
        self.api_key = os.getenv("DID_API_KEY")
        if not self.api_key:
            logger.warning("DID_API_KEY not set - avatar generation will be disabled")
            return
            
        self.base_url = "https://api.d-id.com"
        self.headers = {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json"
        }
        self.storage_service = AzureStorageService()
        
        # Default avatar configurations - production ready avatars
        self.default_avatars = {
            "male": {
                "source_url": "https://create-images-results.d-id.com/DefaultAvatar/male_avatar.jpg",
                "config": {
                    "stitch": True,
                    "fluent": True,
                    "pad_audio": 0.0,
                    "driver_expressions": {
                        "expressions": [
                            {"start_frame": 0, "expression": "neutral", "intensity": 1.0}
                        ]
                    }
                }
            },
            "female": {
                "source_url": "https://create-images-results.d-id.com/DefaultAvatar/female_avatar.jpg",
                "config": {
                    "stitch": True,
                    "fluent": True,
                    "pad_audio": 0.0,
                    "driver_expressions": {
                        "expressions": [
                            {"start_frame": 0, "expression": "neutral", "intensity": 1.0}
                        ]
                    }
                }
            }
        }
    
    async def create_talking_avatar(self, audio_data: bytes, avatar_type: str = "female", user_id: str = None) -> Dict[str, Any]:
        """Create talking avatar video using D-ID with Azure storage integration"""
        try:
            if not self.api_key:
                # Return mock response if D-ID not configured
                return {
                    "video_url": "https://sample-videos.com/zip/10/mp4/SampleVideo_1280x720_1mb.mp4",
                    "talk_id": f"mock_{datetime.now().timestamp()}",
                    "avatar_type": avatar_type,
                    "status": "completed",
                    "timestamp": datetime.now().isoformat(),
                    "mock": True
                }
            
            # Upload audio to D-ID
            audio_url = await self._upload_audio(audio_data, user_id)
            
            # Create talking video
            payload = {
                "source_url": self.default_avatars[avatar_type]["source_url"],
                "script": {
                    "type": "audio",
                    "audio_url": audio_url
                },
                "config": self.default_avatars[avatar_type]["config"]
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/talks",
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code != 201:
                    raise Exception(f"D-ID API error: {response.status_code} - {response.text}")
                
                talk_data = response.json()
                talk_id = talk_data["id"]
                
                logger.info(f"D-ID talk created with ID: {talk_id}")
                
                # Poll for completion
                video_url = await self._wait_for_completion(talk_id)
                
                # Download and upload to Azure storage for CDN delivery
                azure_video_url = await self._cache_video_to_azure(video_url, user_id, talk_id)
                
                return {
                    "video_url": azure_video_url or video_url,  # Fallback to D-ID URL
                    "original_url": video_url,
                    "talk_id": talk_id,
                    "avatar_type": avatar_type,
                    "status": "completed",
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"D-ID Error: {str(e)}")
            raise Exception(f"Avatar generation failed: {str(e)}")
    
    async def _upload_audio(self, audio_data: bytes, user_id: str) -> str:
        """Upload audio file to D-ID and return URL"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                files = {"audio": ("audio.wav", audio_data, "audio/wav")}
                response = await client.post(
                    f"{self.base_url}/clips",
                    headers={"Authorization": self.headers["Authorization"]},
                    files=files
                )
                
                if response.status_code != 201:
                    raise Exception(f"Audio upload failed: {response.status_code} - {response.text}")
                
                audio_url = response.json()["url"]
                logger.info(f"Audio uploaded to D-ID: {audio_url}")
                return audio_url
                
        except Exception as e:
            logger.error(f"Audio upload error: {str(e)}")
            raise
    
    async def _wait_for_completion(self, talk_id: str, max_wait: int = 120) -> str:
        """Wait for D-ID video generation to complete"""
        start_time = datetime.now()
        
        async with httpx.AsyncClient() as client:
            while (datetime.now() - start_time).seconds < max_wait:
                response = await client.get(
                    f"{self.base_url}/talks/{talk_id}",
                    headers=self.headers
                )
                
                if response.status_code != 200:
                    raise Exception(f"Status check failed: {response.status_code}")
                
                data = response.json()
                status = data.get("status")
                
                logger.info(f"D-ID talk {talk_id} status: {status}")
                
                if status == "done":
                    return data.get("result_url")
                elif status == "error":
                    raise Exception(f"D-ID generation failed: {data.get('error', 'Unknown error')}")
                
                # Wait before next check
                await asyncio.sleep(3)
        
        raise Exception("Video generation timeout")
    
    async def _cache_video_to_azure(self, video_url: str, user_id: str, video_id: str) -> Optional[str]:
        """Download video from D-ID and upload to Azure storage for CDN"""
        try:
            if not self.storage_service.blob_service:
                return None
                
            # Download video from D-ID
            async with httpx.AsyncClient() as client:
                response = await client.get(video_url)
                if response.status_code == 200:
                    video_data = response.content
                    
                    # Upload to Azure storage
                    azure_url = await self.storage_service.upload_avatar_video(
                        video_data, user_id, video_id
                    )
                    logger.info(f"Video cached to Azure: {azure_url}")
                    return azure_url
                    
        except Exception as e:
            logger.warning(f"Failed to cache video to Azure: {str(e)}")
            return None

class ServerlessAvatarPipeline:
    """Main serverless pipeline orchestrating all AI services with Azure integration"""
    
    def __init__(self):
        self.stt = STTService()
        self.llm = LLMService()
        self.tts = TTSService()
        self.did = DIDService()
        self.queue_service = RedisQueueService()
        
        # User session storage (Redis-backed in production)
        self.user_sessions = {}
    
    async def process_audio_input(self, audio_data: bytes, user_id: str, avatar_type: str = "female", voice: str = "alloy") -> Dict[str, Any]:
        """Full serverless pipeline: Audio -> STT -> LLM -> TTS -> Avatar"""
        try:
            logger.info(f"Processing audio input for user {user_id}")
            
            # Step 1: Speech to Text
            transcribed_text = await self.stt.transcribe_audio(audio_data)
            logger.info(f"Transcribed: {transcribed_text}")
            
            # Step 2: Generate AI response
            conversation_history = self.user_sessions.get(user_id, [])
            llm_response = await self.llm.generate_response(transcribed_text, user_id, conversation_history)
            
            # Update conversation history
            self._update_conversation_history(user_id, transcribed_text, llm_response["text"])
            
            # Step 3: Text to Speech
            audio_response = await self.tts.synthesize_speech(llm_response["text"], voice, user_id)
            
            # Step 4: Generate talking avatar
            avatar_result = await self._process_avatar_generation(audio_response, avatar_type, user_id)
            
            return {
                "transcribed_text": transcribed_text,
                "ai_response_text": llm_response["text"],
                "avatar_video_url": avatar_result["video_url"],
                "processing_time": datetime.now().isoformat(),
                "tokens_used": llm_response["tokens_used"],
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Pipeline error for user {user_id}: {str(e)}")
            return {
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat()
            }
    
    async def process_text_input(self, text: str, user_id: str, avatar_type: str = "female", voice: str = "alloy") -> Dict[str, Any]:
        """Serverless pipeline for direct text input: Text -> LLM -> TTS -> Avatar"""
        try:
            logger.info(f"Processing text input for user {user_id}: {text}")
            
            # Step 1: Generate AI response
            conversation_history = self.user_sessions.get(user_id, [])
            llm_response = await self.llm.generate_response(text, user_id, conversation_history)
            
            # Update conversation history
            self._update_conversation_history(user_id, text, llm_response["text"])
            
            # Step 2: Text to Speech
            audio_response = await self.tts.synthesize_speech(llm_response["text"], voice, user_id)
            
            # Step 3: Generate talking avatar
            avatar_result = await self._process_avatar_generation(audio_response, avatar_type, user_id)
            
            return {
                "user_input": text,
                "ai_response_text": llm_response["text"],
                "avatar_video_url": avatar_result["video_url"],
                "processing_time": datetime.now().isoformat(),
                "tokens_used": llm_response["tokens_used"],
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Text pipeline error for user {user_id}: {str(e)}")
            return {
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat()
            }
    
    async def _process_avatar_generation(self, audio_data: bytes, avatar_type: str, user_id: str) -> Dict[str, Any]:
        """Process avatar generation with intelligent scaling"""
        try:
            # For now, process immediately - can be enhanced with queueing later
            return await self.did.create_talking_avatar(audio_data, avatar_type, user_id)
                
        except Exception as e:
            logger.error(f"Avatar generation error: {str(e)}")
            raise
    
    def _update_conversation_history(self, user_id: str, user_message: str, ai_response: str):
        """Update conversation history for context"""
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = []
        
        self.user_sessions[user_id].extend([
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": ai_response}
        ])
        
        # Keep only last 20 messages (10 exchanges)
        if len(self.user_sessions[user_id]) > 20:
            self.user_sessions[user_id] = self.user_sessions[user_id][-20:]
    
    async def get_available_voices(self) -> Dict[str, list]:
        """Get available TTS voices"""
        return {
            "openai_voices": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
            "avatar_types": ["male", "female"]
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of all services"""
        health_status = {
            "timestamp": datetime.now().isoformat(),
            "services": {},
            "environment": os.getenv("ENVIRONMENT", "unknown"),
            "processing_mode": os.getenv("PROCESSING_MODE", "immediate")
        }
        
        # Check OpenAI API
        try:
            test_response = await self.llm.generate_response("Hello", "health_check")
            health_status["services"]["llm"] = "healthy"
        except Exception as e:
            health_status["services"]["llm"] = f"unhealthy: {str(e)}"
        
        # Check D-ID API
        try:
            if self.did.api_key:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.did.base_url}/talks",
                        headers=self.did.headers,
                        timeout=10.0
                    )
                    if response.status_code in [200, 401]:
                        health_status["services"]["did"] = "healthy"
                    else:
                        health_status["services"]["did"] = f"unhealthy: HTTP {response.status_code}"
            else:
                health_status["services"]["did"] = "not configured"
        except Exception as e:
            health_status["services"]["did"] = f"unhealthy: {str(e)}"
        
        # Check Azure Storage
        if self.did.storage_service.blob_service:
            health_status["services"]["azure_storage"] = "healthy"
        else:
            health_status["services"]["azure_storage"] = "not configured"
        
        # Check Redis
        try:
            await self.queue_service.connect()
            if self.queue_service.redis_client:
                health_status["services"]["redis"] = "healthy"
            else:
                health_status["services"]["redis"] = "not configured"
        except Exception as e:
            health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        
        return health_status

# Global serverless pipeline instance
avatar_pipeline = ServerlessAvatarPipeline()

# Example usage and testing functions
async def test_serverless_pipeline():
    """Test the complete serverless pipeline"""
    try:
        # Test text input
        result = await avatar_pipeline.process_text_input(
            "Hello, how are you today?", 
            "test_user_123", 
            "female",
            "alloy"
        )
        print("Serverless Pipeline Result:", json.dumps(result, indent=2))
        
        # Test health check
        health = await avatar_pipeline.health_check()
        print("Health Check:", json.dumps(health, indent=2))
        
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    # Run tests
    asyncio.run(test_serverless_pipeline())
