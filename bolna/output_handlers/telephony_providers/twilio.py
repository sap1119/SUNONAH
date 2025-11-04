import base64
import json
import audioop
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from bolna.helpers.logger_config import configure_logger
from bolna.output_handlers.telephony import TelephonyOutputHandler

logger = configure_logger(__name__)
load_dotenv()


class TwilioOutputHandler(TelephonyOutputHandler):
    """Output handler for Twilio telephony provider."""
    
    def __init__(self, websocket: Any = None, mark_event_meta_data: Any = None, 
                 log_dir_name: Optional[str] = None):
        """Initialize Twilio output handler.
        
        Args:
            websocket: WebSocket connection instance
            mark_event_meta_data: Metadata for mark events
            log_dir_name: Directory for logging
        """
        io_provider = 'twilio'
        super().__init__(io_provider, websocket, mark_event_meta_data, log_dir_name)
        self.is_chunking_supported = True

    async def handle_interruption(self) -> None:
        """Handle interruption in the audio stream."""
        logger.info("Interrupting because user spoke in between")
        message_clear = {
            "event": "clear",
            "streamSid": self.stream_sid,
        }
        await self.send_text(json.dumps(message_clear))
        self.mark_event_meta_data.clear_data()

    async def form_media_message(self, audio_data: bytes, audio_format: str = "wav") -> Dict:
        """Form media message for Twilio format.
        
        Args:
            audio_data: Raw audio bytes
            audio_format: Audio format identifier
            
        Returns:
            Formatted media message dictionary
        """
        # Convert to mulaw if not already
        if audio_format != "mulaw":
            logger.info("Converting to mulaw")
            audio_data = audioop.lin2ulaw(audio_data, 2)
            
        base64_audio = self._encode_audio(audio_data)
        
        return {
            'event': 'media',
            'streamSid': self.stream_sid,
            'media': {
                'payload': base64_audio
            }
        }

    async def form_mark_message(self, mark_id: str) -> Dict:
        """Form mark message for Twilio format.
        
        Args:
            mark_id: Unique identifier for the mark
            
        Returns:
            Formatted mark message dictionary
        """
        return {
            "event": "mark",
            "streamSid": self.stream_sid,
            "mark": {
                "name": mark_id
            }
        }