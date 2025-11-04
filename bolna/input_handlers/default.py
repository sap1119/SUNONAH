import asyncio
import base64
import time
import uuid
from starlette.websockets import WebSocketDisconnect

from dotenv import load_dotenv
from bolna.helpers.logger_config import configure_logger
from bolna.helpers.utils import create_ws_data_packet

logger = configure_logger(__name__)
load_dotenv()


from abc import ABC, abstractmethod
from typing import AsyncContextManager, Optional, Dict, Any, AsyncGenerator
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass
class Observable:
    """A simple observable value container."""
    value: Any = None

@dataclass
class InputHandlerConfig:
    """Configuration for input handlers."""
    queues: Dict[str, asyncio.Queue] = field(default_factory=dict)
    websocket: Any = None
    input_types: Dict[str, Any] = field(default_factory=dict)
    mark_event_meta_data: Any = None
    queue: Optional[asyncio.Queue] = None
    turn_based_conversation: bool = False
    conversation_recording: Optional[Dict] = None
    is_welcome_message_played: bool = False
    observable_variables: Dict[str, Observable] = field(default_factory=lambda: defaultdict(Observable))

class BaseInputHandler(AsyncContextManager, ABC):
    """Base class for all input handlers with async context management support."""
    
    def __init__(self, config: Optional[InputHandlerConfig] = None):
        """Initialize the input handler with optional configuration."""
        self.config = config or InputHandlerConfig()
        self.queues = self.config.queues or {}
        self.websocket = self.config.websocket
        self.input_types = self.config.input_types or {}
        self.websocket_listen_task = None
        self.running = True
        self.turn_based_conversation = self.config.turn_based_conversation
        self.queue = self.config.queue
        self.conversation_recording = self.config.conversation_recording or {}
        self.is_welcome_message_played = self.config.is_welcome_message_played
        self.response_heard_by_user = ""
        self._is_audio_being_played_to_user = False
        self.observable_variables = self.config.observable_variables
        self.mark_event_meta_data = self.config.mark_event_meta_data
        self.audio_chunks_received = 0
        self.update_start_ts = time.time()
        self.io_provider = 'default'
        self.is_dtmf_active = False
        self.dtmf_digits = ""
        self._initialized = False
        
    @abstractmethod
    async def listen_impl(self) -> None:
        """Abstract method for listening to input."""
        pass
        
    @abstractmethod
    async def process_message_impl(self, message: Dict) -> Optional[Dict]:
        """Abstract method for processing messages."""
        pass
        
    @abstractmethod
    async def stop_handler_impl(self) -> None:
        """Abstract method for stopping the handler."""
        pass

    async def __aenter__(self):
        """Async context entry."""
        try:
            await self.initialize()
            self._initialized = True
            return self
        except Exception as e:
            logger.error(f"Error initializing input handler: {e}")
            await self.__aexit__(type(e), e, e.__traceback__)
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context exit."""
        try:
            await self.cleanup()
        except Exception as e:
            logger.error(f"Error during input handler cleanup: {e}")
        finally:
            self._initialized = False
            
    async def initialize(self):
        """Initialize any resources needed by the handler."""
        if self.websocket_listen_task is None:
            self.websocket_listen_task = asyncio.create_task(self.listen_impl())
        
    async def cleanup(self):
        """Clean up any resources used by the handler."""
        await self.stop_handler_impl()
        if self.websocket_listen_task:
            try:
                self.websocket_listen_task.cancel()
                await self.websocket_listen_task
            except asyncio.CancelledError:
                pass
            self.websocket_listen_task = None

class DefaultInputHandler(BaseInputHandler):
    """Default implementation of the input handler."""
    
    async def listen_impl(self) -> None:
        """Listen for incoming messages."""
        try:
            while self.running:
                if self.queue is not None:
                    logger.info("Listening to queue")
                    request = await self.queue.get()
                elif self.websocket is not None:
                    request = await self.websocket.receive_json()
                else:
                    await asyncio.sleep(0.1)
                    continue
                
                try:
                    await self.process_message(request)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
            await self._handle_disconnect()
            
        except Exception as e:
            logger.error(f"Error in listen loop: {e}")
            await self._handle_disconnect()
            
    async def _handle_disconnect(self) -> None:
        """Handle disconnection events."""
        try:
            if 'transcriber' in self.queues:
                await self.queues['transcriber'].put(create_ws_data_packet(
                    data=None,
                    meta_info={'io': 'default', 'eos': True}
                ))
        except Exception as e:
            logger.error(f"Error handling disconnect: {e}")
        finally:
            self.running = False
            
    async def stop_handler_impl(self) -> None:
        """Stop the input handler."""
        self.running = False
        if self.websocket is not None:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error closing websocket: {e}")
                
    async def process_message_impl(self, message: Dict) -> Optional[Dict]:
        """Process incoming messages."""
        try:
            if not isinstance(message, dict) or 'type' not in message:
                return {"error": "Invalid message format"}
                
            msg_type = message.get('type')
            
            if msg_type == 'audio' and 'data' in message:
                await self._process_audio(message['data'])
                
            elif msg_type == 'text' and 'data' in message:
                await self._process_text(message['data'])
                
            elif msg_type == 'mark':
                await self._process_mark_event(message)
                
            elif msg_type == 'init':
                await self._process_init_event(message)
                
            else:
                return {"error": "Unsupported message type"}
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            return {"error": str(e)}
            
    async def _process_audio(self, audio_data: str) -> None:
        """Process audio data."""
        try:
            data = base64.b64decode(audio_data)
            if self.queues and 'transcriber' in self.queues:
                packet = create_ws_data_packet(
                    data=data,
                    meta_info={
                        'io': 'default',
                        'type': 'audio',
                        'sequence': self.input_types.get('audio')
                    }
                )
                
                if self.conversation_recording:
                    if self.conversation_recording.get("metadata", {}).get("started", 0) == 0:
                        self.conversation_recording["metadata"]["started"] = time.time()
                    self.conversation_recording.get('input', {})['data'] = data
                    
                await self.queues['transcriber'].put(packet)
                
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            
    async def _process_text(self, text: str) -> None:
        """Process text data."""
        try:
            if self.queues and 'llm' in self.queues:
                packet = create_ws_data_packet(
                    data=text,
                    meta_info={
                        'io': 'default',
                        'type': 'text',
                        'sequence': self.input_types.get('audio'),
                        'bypass_synth': self.turn_based_conversation
                    }
                )
                await self.queues['llm'].put(packet)
                
        except Exception as e:
            logger.error(f"Error processing text: {e}")
            
    async def _process_mark_event(self, message: Dict) -> None:
        """Process mark events."""
        try:
            if self.mark_event_meta_data:
                mark_id = message.get("name")
                meta_data = self.mark_event_meta_data.fetch_data(mark_id)
                
                if meta_data:
                    message_type = meta_data.get("type")
                    
                    if message_type == "pre_mark_message":
                        self.update_is_audio_being_played(True)
                        return
                        
                    self.audio_chunks_received += 1
                    self.response_heard_by_user += meta_data.get("text_synthesized", "")
                    
                    if meta_data.get("is_final_chunk"):
                        if (message_type != "is_user_online_message" and 
                            "final_chunk_played_observable" in self.observable_variables):
                            self.observable_variables["final_chunk_played_observable"].value = not self.observable_variables["final_chunk_played_observable"].value
                            
                        self.update_is_audio_being_played(False)
                        
                        if message_type == "agent_welcome_message":
                            self.audio_chunks_received = 0
                            self.is_welcome_message_played = True
                            
                        elif message_type == "agent_hangup" and "agent_hangup_observable" in self.observable_variables:
                            self.observable_variables["agent_hangup_observable"].value = True
                            
        except Exception as e:
            logger.error(f"Error processing mark event: {e}")
            
    async def _process_init_event(self, message: Dict) -> None:
        """Process initialization events."""
        try:
            init_observable = self.observable_variables.get("init_event_observable")
            if init_observable is not None:
                init_observable.value = message.get("meta_data")
        except Exception as e:
            logger.error(f"Error processing init event: {e}")

    def get_audio_chunks_received(self):
        audio_chunks_received = self.audio_chunks_received
        self.audio_chunks_received = 0
        return audio_chunks_received
        
    def update_is_audio_being_played(self, value):
        logger.info(f"Audio is being updated - {value}")
        if value is True:
            self.update_start_ts = time.time()
            logger.info(f"updating ts as mark_message received: {self.update_start_ts}")
        self._is_audio_being_played_to_user = value

    def is_audio_being_played_to_user(self):
        return self._is_audio_being_played_to_user

    def get_response_heard_by_user(self):
        response = self.response_heard_by_user
        self.response_heard_by_user = ""
        return response.strip()

    async def stop_handler(self):
        self.running = False
        try:
            if not self.queue:
                await self.websocket.close()
        except Exception as e:
            logger.error(f"Error closing WebSocket: {e}")

    def get_stream_sid(self):
        return str(uuid.uuid4())

    def get_current_mark_started_time(self):
        return self.update_start_ts

    def welcome_message_played(self):
        return self.is_welcome_message_played

    def get_mark_event_meta_data_obj(self, packet):
        mark_id = packet["name"]
        return self.mark_event_meta_data.fetch_data(mark_id)

    def process_mark_message(self, packet):
        mark_event_meta_data_obj = self.get_mark_event_meta_data_obj(packet)
        if not mark_event_meta_data_obj:
            logger.info(f"No object retrieved from global dict of mark_event_meta_data for received mark event - {packet}")
            return

        logger.info(f"Mark event meta data object retrieved = {mark_event_meta_data_obj}")
        message_type = mark_event_meta_data_obj.get("type")
        
        is_content_audio = message_type not in ['ambient_noise', 'backchanneling']

        if message_type == "pre_mark_message":
            self.update_is_audio_being_played(True)
            return

        self.audio_chunks_received += 1
        self.response_heard_by_user += mark_event_meta_data_obj.get("text_synthesized")

        if mark_event_meta_data_obj.get("is_final_chunk"):
            if message_type != "is_user_online_message":
                self.observable_variables["final_chunk_played_observable"].value = not self.observable_variables["final_chunk_played_observable"].value
            self.update_is_audio_being_played(False)

            if message_type == "agent_welcome_message":
                logger.info("Received mark event for agent_welcome_message")
                self.audio_chunks_received = 0
                self.is_welcome_message_played = True

            elif message_type == "agent_hangup":
                logger.info(f"Agent hangup has been triggered")
                self.observable_variables["agent_hangup_observable"].value = True

    # Legacy methods removed - using the new _process_* methods with proper async support

    async def process_message(self, message):
        # TODO check what condition needs to be added over here
        # if message['type'] not in self.input_types.keys() and not self.turn_based_conversation:
        #     logger.info(f"straight away returning")
        #     return {"message": "invalid input type"}

        try:
            return await self.process_message_impl(message)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {"error": str(e)}
            
    async def handle(self):
        """Initialize the handler and start listening."""
        await self.initialize()