import copy
import time
import uuid
import asyncio
import traceback

from .base_manager import BaseManager
from .task_manager import TaskManager
from bolna.helpers.logger_config import configure_logger
from bolna.models import AGENT_WELCOME_MESSAGE
from bolna.helpers.utils import update_prompt_with_context

logger = configure_logger(__name__)


class AssistantManager(BaseManager):
    def __init__(self, agent_config, ws=None, assistant_id=None, context_data=None, conversation_history=None,
                 turn_based_conversation=None, cache=None, input_queue=None, output_queue=None, **kwargs):
        super().__init__()
        self.run_id = str(uuid.uuid4())
        self.assistant_id = assistant_id
        self.tools = {}
        self.websocket = ws
        self.agent_config = agent_config
        self.context_data = context_data
        self.tasks = agent_config.get('tasks', [])
        self.task_states = [False] * len(self.tasks)
        self.turn_based_conversation = turn_based_conversation
        self.cache = cache
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.kwargs = kwargs
        self.conversation_history = conversation_history
        if kwargs.get("is_web_based_call", False):
            self.kwargs['agent_welcome_message'] = agent_config.get('agent_welcome_message', AGENT_WELCOME_MESSAGE)
        else:
            self.kwargs['agent_welcome_message'] = update_prompt_with_context(
                agent_config.get('agent_welcome_message', AGENT_WELCOME_MESSAGE), context_data)

    async def run(self, local=False, run_id=None):
        """
        Run will start all tasks in sequential format with proper resource management
        and error handling.
        """
        if run_id:
            self.run_id = run_id

        input_parameters = None
        task_managers = []
        
        try:
            for task_id, task in enumerate(self.tasks):
                logger.info(f"Running task {task_id}")
                
                # Get consistent agent name
                agent_name = self.agent_config.get("agent_name") or self.agent_config.get("assistant_name")
                if not agent_name:
                    agent_name = f"agent_{self.run_id}"
                    logger.warning(f"No agent name provided, using generated name: {agent_name}")
                
                # Create task manager with proper timeout
                try:
                    async with asyncio.timeout(300):  # 5 minute timeout per task
                        # Create task manager with correct parameters
                        task_manager = TaskManager(
                            task=task,  # Pass the task configuration
                            session_id=str(self.run_id),  # Use run_id as session_id
                            sequence_id=str(task_id)  # Use task_id as sequence_id
                        )
                        
                        task_managers.append(task_manager)
                        
                        # Load prompt with timeout
                        await task_manager.load_prompt(agent_name, task_id, local=local, **self.kwargs)
                        
                        # Run task with resource monitoring
                        task_output = await task_manager.run()
                        if not task_output:
                            raise Exception(f"Task {task_id} failed to produce output")
                            
                        task_output['run_id'] = self.run_id
                        task_output['task_id'] = task_id
                        task_output['timestamp'] = time.time()
                        
                        yield task_id, copy.deepcopy(task_output)
                        
                        # Update task state and parameters
                        self.task_states[task_id] = True
                        if task_id == 0:
                            input_parameters = task_output
                        if task.get("task_type") == "extraction" and "extracted_data" in task_output:
                            input_parameters = input_parameters or {}
                            input_parameters["extraction_details"] = task_output["extracted_data"]
                            
                except asyncio.TimeoutError:
                    logger.error(f"Task {task_id} timed out")
                    raise Exception(f"Task {task_id} execution timed out")
                except Exception as e:
                    logger.error(f"Task {task_id} failed: {str(e)}")
                    logger.error(f"Stack trace: {traceback.format_exc()}")
                    raise
                    
        except Exception as e:
            logger.error(f"Agent execution failed: {str(e)}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            raise
            
        finally:
            # Cleanup all task managers
            for tm in task_managers:
                try:
                    await tm.cleanup()
                except Exception as e:
                    logger.error(f"Failed to cleanup task manager: {str(e)}")
                    
            logger.info(f"Done with execution of agent {agent_name} (run_id: {self.run_id})")