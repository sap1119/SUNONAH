from bolna.models import *
from bolna.agent_manager import AssistantManager

class Assistant:
    def __init__(self, name = "trial_agent"):
        self.name = name
        self.tasks = []

    def add_task(self, task_type, llm_agent, input_queue=None, output_queue=None, transcriber=None, synthesizer=None, enable_textual_input=False):
        pipelines = []
        
        # Build the main pipeline
        pipeline = []
        if transcriber is not None:
            pipeline.append("transcriber")
        pipeline.append("llm")
        if synthesizer is not None:
            pipeline.append("synthesizer")
        pipelines.append(pipeline)
        
        # Add text-only pipeline if enabled
        if enable_textual_input:
            pipelines.append(["llm"])
        
        # Create the toolchain model
        toolchain = ToolsChainModel(
            execution="parallel",
            pipelines=pipelines
        )
        
        # Create the tools configuration
        tools_config = ToolsConfig(
            input={"format": "wav", "provider": "default"},
            output={"format": "wav", "provider": "default"},
            llm_agent=llm_agent,
            transcriber=transcriber,
            synthesizer=synthesizer
        )
        
        # Create and add the task
        task = Task(
            task_type=task_type,
            toolchain=toolchain,
            tools_config=tools_config,
            enable_textual_input=enable_textual_input
        ).dict()
        self.tasks.append(task)


    async def execute(self): 
        agent_config = {
            "agent_name": self.name,
            "tasks": self.tasks
        }
        self.manager = AssistantManager(agent_config, ws= None, input_queue = None, output_queue = None)
        async for index, task_output in self.manager.run():
            yield task_output
