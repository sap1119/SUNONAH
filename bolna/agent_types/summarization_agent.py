import traceback
from .base_agent import BaseAgent
from bolna.helpers.logger_config import configure_logger

logger = configure_logger(__name__)


class SummarizationAgent(BaseAgent):
    def __init__(self, llm, summarization_prompt):
        super().__init__()
        self.llm = llm
        self.summarization_prompt = summarization_prompt

    async def generate(self, history):
        try:
            logger.info("Generating summary")
            message = [{"role": "system", "content": self.summarization_prompt}] + history
            response = await self.llm.generate(message, request_json=True)
            return response
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error generating summary: {e}")
            return None