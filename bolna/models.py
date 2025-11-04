from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union
from enum import Enum

# Default welcome message for agents
AGENT_WELCOME_MESSAGE = """Hello! I'm your AI assistant. How can I help you today?"""


class TranscriberProvider(str, Enum):
    DEEPGRAM = "deepgram"
    AZURE = "azure"
    GOOGLE = "google"


class SynthesizerProvider(str, Enum):
    ELEVENLABS = "elevenlabs"
    AZURE = "azure"
    POLLY = "polly"


class LlmProvider(str, Enum):
    OPENAI = "openai"
    AZURE = "azure"
    ANTHROPIC = "anthropic"


class AgentType(str, Enum):
    SIMPLE_LLM_AGENT = "simple_llm_agent"
    CONTEXTUAL_AGENT = "contextual_agent"
    EXTRACTION_AGENT = "extraction_agent"
    GRAPH_AGENT = "graph_agent"
    WEBHOOK_AGENT = "webhook_agent"


class AgentFlowType(str, Enum):
    STREAMING = "streaming"
    NON_STREAMING = "non_streaming"


class ElevenLabsConfig(BaseModel):
    voice: str
    voice_id: str
    model: str = "eleven_turbo_v2_5"


class AzureSynthesizerConfig(BaseModel):
    voice: str
    style: Optional[str] = None
    style_degree: Optional[float] = None
    role: Optional[str] = None


class PollyConfig(BaseModel):
    voice: str
    engine: str = "neural"


class SimpleLlmAgent(BaseModel):
    provider: LlmProvider
    model: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    functions: Optional[List[Dict[str, Any]]] = None
    provider_config: Optional[Dict[str, Any]] = None


class Transcriber(BaseModel):
    provider: TranscriberProvider
    model: Optional[str] = None
    stream: bool = False
    language: str = "en"
    provider_config: Optional[Dict[str, Any]] = None


class Synthesizer(BaseModel):
    provider: SynthesizerProvider
    provider_config: Optional[Union[ElevenLabsConfig, AzureSynthesizerConfig, PollyConfig]] = None
    stream: bool = False
    audio_format: str = "wav"


class LlmAgent(BaseModel):
    agent_type: AgentType
    agent_flow_type: AgentFlowType = AgentFlowType.NON_STREAMING
    llm_config: SimpleLlmAgent


class ToolsChainModel(BaseModel):
    execution: str
    pipelines: List[List[str]]

class ToolsConfig(BaseModel):
    input: Dict[str, Any]
    output: Dict[str, Any]
    llm_agent: LlmAgent
    transcriber: Optional[Transcriber] = None
    synthesizer: Optional[Synthesizer] = None

class Task(BaseModel):
    task_type: str = "conversation"
    toolchain: ToolsChainModel
    tools_config: ToolsConfig
    enable_textual_input: bool = False