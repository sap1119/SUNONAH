import base64
import json
import uuid
import audioop
import time
import traceback
from abc import abstractmethod
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from bolna.helpers.logger_config import configure_logger
from .default import DefaultOutputHandler

logger = configure_logger(__name__)
load_dotenv()


class TelephonyOutputHandler(DefaultOutputHandler):
    """Base class for all telephony output handlers."""
    
    def __init__(self, io_provider: str, websocket: Any = None, 
                 mark_event_meta_data: Any = None, log_dir_name: Optional[str] = None):
        """Initialize telephony output handler.
        
        Args:
            io_provider: Telephony provider identifier
            websocket: WebSocket connection instance
            mark_event_meta_data: Metadata for mark events
            log_dir_name: Directory for logging
        """
        super().__init__(io_provider=io_provider, websocket=websocket,
                        mark_event_meta_data=mark_event_meta_data)
        self.stream_sid = None
        self.current_request_id = None
        self.rejected_request_ids = set()

    @abstractmethod
    async def form_media_message(self, audio_data: bytes, audio_format: str) -> Dict:
        """Form media message for telephony provider.
        
        Args:
            audio_data: Raw audio bytes
            audio_format: Audio format identifier
            
        Returns:
            Formatted media message dictionary
        """
        raise NotImplementedError()

    @abstractmethod
    async def form_mark_message(self, mark_id: str) -> Dict:
        """Form mark message for telephony provider.
        
        Args:
            mark_id: Unique identifier for the mark
            
        Returns:
            Formatted mark message dictionary
        """
        raise NotImplementedError()

    async def set_stream_sid(self, stream_id: str) -> None:
        """Set the stream session ID.
        
        Args:
            stream_id: Stream session identifier
        """
        self.stream_sid = stream_id

    async def handle(self, ws_data_packet: Dict) -> None:
        """Handle websocket data packet.
        
        Args:
            ws_data_packet: Data packet from websocket
        """
        try:
            audio_chunk = ws_data_packet.get('data', b'')
            meta_info = ws_data_packet.get('meta_info', {})
            
            # Set stream ID if not set
            if self.stream_sid is None:
                self.stream_sid = meta_info.get('stream_sid')

            try:
                # Handle special case for 1-byte audio chunks
                if len(audio_chunk) == 1:
                    audio_chunk += b'\x00'

                if audio_chunk and self.stream_sid and len(audio_chunk) != 1:
                    if audio_chunk != b'\x00\x00':
                        audio_format = meta_info.get("format", "wav")
                        
                        # Send pre-mark message
                        await self._handle_pre_mark_message()

                        # Handle special case for Plivo welcome message
                        if (audio_format == 'pcm' and 
                            meta_info.get('message_category') == 'agent_welcome_message' and 
                            self.io_provider == 'plivo' and 
                            meta_info.get('cached', False)):
                            audio_format = 'wav'

                        # Send media message
                        media_message = await self.form_media_message(audio_chunk, audio_format)
                        await self.send_text(json.dumps(media_message))
                        
                        # Update welcome message timestamp if needed
                        if (meta_info.get('message_category') == 'agent_welcome_message' and 
                            not self.welcome_message_sent_ts):
                            self.welcome_message_sent_ts = time.time() * 1000
                        
                        logger.info(f"Sent media event - {meta_info.get('mark_id')}")

                    # Send post-mark message
                    if meta_info:
                        await self._handle_post_mark_message(meta_info, audio_chunk)
                else:
                    logger.info("Not sending - invalid audio chunk")

            except Exception as e:
                traceback.print_exc()
                logger.error(f'Error in message handling: {str(e)}')

        except Exception as e:
            logger.error(f'Error in telephony handling: {str(e)}')
            
    async def _handle_pre_mark_message(self) -> None:
        """Handle pre-mark message for audio data."""
        pre_mark_event_meta_data = {"type": "pre_mark_message"}
        mark_id = str(uuid.uuid4())
        self.mark_event_meta_data.update_data(mark_id, pre_mark_event_meta_data)
        mark_message = await self.form_mark_message(mark_id)
        logger.info(f"Sending pre-mark event - {mark_message}")
        await self.send_text(json.dumps(mark_message))
        
    async def _handle_post_mark_message(self, meta_info: Dict, audio_chunk: bytes) -> None:
        """Handle post-mark message for audio data.
        
        Args:
            meta_info: Metadata about the audio packet
            audio_chunk: The audio data bytes
        """
        duration = (len(audio_chunk) / 8000 
                   if meta_info.get('format', 'mulaw') == 'mulaw' 
                   else len(audio_chunk) / 16000)
                   
        mark_event_meta_data = self._create_mark_event_metadata(
            meta_info, 
            duration=duration
        )
        
        mark_id = (meta_info.get("mark_id") 
                  if (meta_info.get("mark_id") and meta_info.get("mark_id") != "") 
                  else str(uuid.uuid4()))
                  
        logger.info(f"Mark meta data for {mark_id}: {mark_event_meta_data}")
        self.mark_event_meta_data.update_data(mark_id, mark_event_meta_data)
        
        mark_message = await self.form_mark_message(mark_id)
        logger.info(f"Sending post-mark event - {mark_message}")
        await self.send_text(json.dumps(mark_message))