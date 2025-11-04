import json
import time
import uuid
from typing import Dict, Optional, Any
from dotenv import load_dotenv
from bolna.helpers.logger_config import configure_logger
from .base_handler import BaseOutputHandler

logger = configure_logger(__name__)
load_dotenv()


class DefaultOutputHandler(BaseOutputHandler):
    """Default output handler implementation."""
    
    def __init__(self, io_provider: str = 'default', websocket: Any = None, 
                 queue: Any = None, is_web_based_call: bool = False, 
                 mark_event_meta_data: Any = None):
        """Initialize the default output handler.
        
        Args:
            io_provider: Provider identifier string
            websocket: WebSocket connection instance
            queue: Message queue for async processing
            is_web_based_call: Whether this is a web-based call
            mark_event_meta_data: Metadata for mark events
        """
        super().__init__(io_provider, websocket, is_web_based_call, mark_event_meta_data)
        self.queue = queue

    async def handle_interruption(self) -> None:
        """Handle interruption by sending clear signal."""
        response = {"data": None, "type": "clear"}
        await self.send_json(response)

    async def handle(self, packet: Dict) -> None:
        """Handle output packet processing.
        
        Args:
            packet: The data packet to process
            
        The packet should contain:
            - data: The actual payload (audio/text)
            - meta_info: Metadata about the packet
        """
        try:
            logger.info("Packet received")
            
            data = None
            meta_info = packet["meta_info"]
            
            if meta_info['type'] in ('audio', 'text'):
                # Process audio data
                if meta_info['type'] == 'audio':
                    logger.info("Sending audio")
                    data = self._encode_audio(packet['data'])
                # Process text data
                elif meta_info['type'] == 'text':
                    logger.info(f"Sending text response {packet['data']}")
                    data = packet['data']

                # Handle pre-mark message for audio
                if meta_info['type'] == 'audio':
                    await self._handle_pre_mark_message()

                # Update welcome message timestamp if needed
                if (packet['meta_info'].get('message_category') == 'agent_welcome_message' 
                    and not self.welcome_message_sent_ts):
                    self.welcome_message_sent_ts = time.time() * 1000

                # Send the main response
                response = {"data": data, "type": meta_info['type']}
                await self.send_json(response)

                # Handle post-mark message for audio
                if meta_info['type'] == 'audio':
                    await self._handle_post_mark_message(meta_info)
            else:
                logger.error("Other modalities are not implemented yet")
                
        except Exception as e:
            logger.error(f"Error in output handling: {e}")

    async def _handle_pre_mark_message(self) -> None:
        """Handle pre-mark message for audio data."""
        pre_mark_event_meta_data = {
            "type": "pre_mark_message",
        }
        mark_id = str(uuid.uuid4())
        self.mark_event_meta_data.update_data(mark_id, pre_mark_event_meta_data)
        mark_message = {
            "type": "mark",
            "name": mark_id
        }
        logger.info(f"Sending pre-mark event - {mark_message}")
        await self.send_text(json.dumps(mark_message))

    async def _handle_post_mark_message(self, meta_info: Dict) -> None:
        """Handle post-mark message for audio data.
        
        Args:
            meta_info: Metadata about the audio packet
        """
        mark_id = (meta_info.get("mark_id") 
                  if (meta_info.get("mark_id") and meta_info.get("mark_id") != "") 
                  else str(uuid.uuid4()))
                  
        mark_event_meta_data = self._create_mark_event_metadata(meta_info)
        
        logger.info(f"Mark meta data being saved for mark id - {mark_id} is - {mark_event_meta_data}")
        self.mark_event_meta_data.update_data(mark_id, mark_event_meta_data)
        
        mark_message = {
            "type": "mark",
            "name": mark_id
        }
        logger.info(f"Sending post-mark event - {mark_message}")
        await self.send_text(json.dumps(mark_message))