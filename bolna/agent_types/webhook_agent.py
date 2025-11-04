import json
import traceback
from .base_agent import BaseAgent
from bolna.helpers.logger_config import configure_logger
from bolna.helpers.utils import update_prompt_with_context

logger = configure_logger(__name__)


class WebhookAgent(BaseAgent):
    def __init__(self, llm, webhook_prompt, context_data=None):
        super().__init__()
        self.llm = llm
        self.webhook_prompt = webhook_prompt
        self.context_data = context_data

    async def generate(self, history, webhook_config):
        try:
            webhook_prompt = update_prompt_with_context(self.webhook_prompt, self.context_data)
            message = [{"role": "system", "content": webhook_prompt}] + history
            webhook_response = await self.llm.generate(message, request_json=True)
            
            webhook_data = json.loads(webhook_response)
            webhook_data.update(webhook_config)
            
            logger.info(f"Generated webhook data: {webhook_data}")
            return webhook_data
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error generating webhook data: {e}")
            return None