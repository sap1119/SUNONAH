from abc import ABC, abstractmethod
import json
import base64
import time
import uuid
import logging
from typing import Any, Dict, Optional

from bolna.helpers.logger_config import configure_logger

logger = configure_logger(__name__)


from typing import AsyncContextManager

class BaseOutputHandler(AsyncContextManager, ABC):
    """Base class for all output handlers with async context management support."""
    
    def __init__(self, io_provider: str = 'default', websocket: Any = None, 
                 is_web_based_call: bool = False, mark_event_meta_data: Any = None):
        """Initialize the base output handler.
        
        Args:
            io_provider: Provider identifier string
            websocket: WebSocket connection instance
            is_web_based_call: Whether this is a web-based call
            mark_event_meta_data: Metadata for mark events
        """
        self.websocket = websocket
        self.io_provider = io_provider
        self.is_web_based_call = is_web_based_call
        self.mark_event_meta_data = mark_event_meta_data
        self._initialized = False

    async def __aenter__(self):
        """Async context entry."""
        try:
            await self.initialize()
            self._initialized = True
            return self
        except Exception as e:
            logger.error(f"Error initializing output handler: {e}")
            await self.__aexit__(type(e), e, e.__traceback__)
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context exit."""
        try:
            await self.cleanup()
        except Exception as e:
            logger.error(f"Error during output handler cleanup: {e}")
        finally:
            self._initialized = False
            
    async def initialize(self):
        """Initialize any resources needed by the handler."""
        pass
        
    async def cleanup(self):
        """Clean up any resources used by the handler."""
        pass
        
        # State tracking
        self.is_chunking_supported = True
        self.is_interruption_task_on = False
        self.is_last_hangup_chunk_sent = False
        self.welcome_message_sent_ts = None
        
    async def send_json(self, data: Dict) -> None:
        """Send JSON data over the websocket."""
        if self.websocket:
            await self.websocket.send_json(data)
            
    async def send_text(self, text: str) -> None:
        """Send text data over the websocket."""
        if self.websocket:
            await self.websocket.send_text(text)
            
    def _encode_audio(self, audio_data: bytes) -> str:
        """Encode audio data to base64 string."""
        return base64.b64encode(audio_data).decode("utf-8")
        
    @abstractmethod
    async def handle(self, packet: Dict) -> None:
        """Handle an output packet.
        
        Args:
            packet: The data packet to handle
        """
        pass
        
    @abstractmethod
    async def handle_interruption(self) -> None:
        """Handle interruption in the output stream."""
        pass
        
    def process_in_chunks(self, yield_chunks: bool = False) -> bool:
        """Check if chunking is supported and enabled."""
        return self.is_chunking_supported and yield_chunks
        
    def get_provider(self) -> str:
        """Get the IO provider identifier."""
        return self.io_provider
        
    def set_hangup_sent(self) -> None:
        """Mark hangup as sent."""
        self.is_last_hangup_chunk_sent = True
        
    def hangup_sent(self) -> bool:
        """Check if hangup was sent."""
        return self.is_last_hangup_chunk_sent
        
    def get_welcome_message_sent_ts(self) -> Optional[float]:
        """Get timestamp of welcome message."""
        return self.welcome_message_sent_ts
        
    async def send_init_acknowledgement(self) -> None:
        """Send initialization acknowledgement."""
        data = {"type": "ack"}
        logger.info("Sending ack event")
        await self.send_text(json.dumps(data))
        
    def _create_mark_event_metadata(self, meta_info: Dict, 
                                  event_type: str = "post_mark_message", 
                                  duration: Optional[float] = None) -> Dict:
        """Create metadata for mark events.
        
        Args:
            meta_info: Message metadata
            event_type: Type of mark event
            duration: Audio duration if applicable
            
        Returns:
            Dict containing mark event metadata
        """
        metadata = {
            "text_synthesized": "" if meta_info["sequence_id"] == -1 
                              else meta_info.get("text_synthesized", ""),
            "type": meta_info.get('message_category', ''),
            "is_first_chunk": meta_info.get("is_first_chunk", False),
            "is_final_chunk": meta_info.get("end_of_llm_stream", False) 
                            and meta_info.get("end_of_synthesizer_stream", False),
            "sequence_id": meta_info["sequence_id"]
        }
        
        if duration is not None:
            metadata["duration"] = duration
            
        return metadata