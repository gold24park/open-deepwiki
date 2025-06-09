from typing import Annotated, Dict, Sequence, TypedDict
from uuid import uuid4

from langchain.schema import BaseMessage, HumanMessage, SystemMessage
from langchain.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt.chat_agent_executor import StructuredResponseSchema

from apps.git import GitRepository
from apps.settings import CONFIG, IS_TEST
from apps.tools.code_index_search import CodeIndexSearchTool
from apps.tools.list_files import ListFilesTool
from apps.tools.semantic_search_files import SemanticSearchFilesTool
from apps.tools.view_file_content import ViewFileContentTool


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    number_of_steps: int
    structured_response: str | None


def create_react_agent(
    prompt: str,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    response_format: StructuredResponseSchema | None = None,
):
    system_prompt = SystemMessage(prompt)

    model_runnable = model.bind_tools(tools)

    tools_by_name = {tool.name: tool for tool in tools}

    async def call_tool(state: AgentState):
        outputs = []
        for tool_call in state["messages"][-1].tool_calls:  # type: ignore
            tool_result = await tools_by_name[tool_call["name"]].ainvoke(
                tool_call["args"]
            )
            outputs.append(
                ToolMessage(
                    content=tool_result,
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}

    async def call_model(state: AgentState, config: RunnableConfig):
        steps = state.get("number_of_steps", 0)
        response = await model_runnable.ainvoke(
            [system_prompt] + state["messages"],  # type: ignore
            config,
        )
        return {"messages": [response], "number_of_steps": steps + 1}

    def should_continue(state: AgentState, config: RunnableConfig):
        messages = state["messages"]
        step_limit = config["configurable"].get("step_limit", 20)  # type: ignore
        # If the last message is not a tool call, end the conversation
        if not messages[-1].tool_calls:  # type: ignore
            return "end"
        # If the allowed steps have been reached, need to provide a final answer based on the conversation
        if state.get("number_of_steps", 0) >= step_limit:
            return "final_answer"
        return "continue"

    async def call_final_answer(state: AgentState, config: RunnableConfig):
        messages = (
            [system_prompt]
            + state["messages"][:-1]  # type: ignore
            + [
                SystemMessage(  # type: ignore
                    content="You have reached the maximum number of steps. "
                    "Please provide a final answer based on the conversation so far."
                )
            ]
        )
        response = await model.ainvoke(messages, config)
        return {"messages": [response]}

    async def generate_structured_response(
        state: AgentState, config: RunnableConfig
    ):
        model_with_structured_output = model.with_structured_output(
            response_format  # type: ignore
        )
        response = await model_with_structured_output.ainvoke(
            state["messages"], config
        )
        return {"structured_response": response}

    final_node = "generate_structured_response" if response_format else END

    workflow = StateGraph(AgentState)

    workflow.add_node("model", call_model)
    workflow.add_node("tools", call_tool)
    workflow.add_node("final_answer", call_final_answer)

    if response_format:
        workflow.add_node(
            "generate_structured_response", generate_structured_response
        )
        workflow.add_edge("generate_structured_response", END)

    workflow.set_entry_point("model")

    workflow.add_conditional_edges(
        "model",
        should_continue,
        {
            "continue": "tools",
            "final_answer": "final_answer",
            "end": final_node,
        },
    )

    workflow.add_edge("tools", "model")
    workflow.add_edge("final_answer", final_node)

    graph = workflow.compile(checkpointer=MemorySaver())
    return graph


class AgentBuilder:
    def __init__(
        self,
        repo: GitRepository,
        model_config: Dict,
        response_format: StructuredResponseSchema | None,
    ):
        self.system_prompt = open(CONFIG["agent"]["prompt"]).read()
        self.repo = repo
        self.response_format = response_format

        self.model = self.setup_model(model_config)
        self.tools = self.setup_tools(repo)

    def setup_model(self, model_config: Dict) -> BaseChatModel:
        # 모델 설정
        model_config = (
            {"model": "openai/gpt-4.1-nano"} if IS_TEST else model_config
        )
        model_cls = {
            "openai": ChatOpenAI,
            "google": ChatGoogleGenerativeAI,
            "anthropic": ChatAnthropic,
        }
        company, model_name = model_config["model"].split("/")

        # 모델 인스턴스화
        model: BaseChatModel = model_cls[company](
            model=model_name,
            temperature=model_config.get("temperature", 0),
            top_p=model_config.get("top_p", 1),
        )
        return model

    def setup_tools(self, repo: GitRepository) -> Sequence[BaseTool]:
        """
        Setup tools to be used by the agent.
        """
        tools = [
            SemanticSearchFilesTool(repo=repo),
            CodeIndexSearchTool(repo=repo),
            ViewFileContentTool(repo=repo),
            ListFilesTool(repo=repo),
        ]
        return tools

    def build(self) -> CompiledStateGraph:
        agent = create_react_agent(
            prompt=self.system_prompt,
            model=self.model,
            tools=self.tools,
            response_format=self.response_format,
        )
        return agent


async def complete_chat(
    prompt: str,
    repo: GitRepository,
    model_config: Dict = {"model": "openai/gpt-4o"},
    response_format: StructuredResponseSchema | None = None,
    debug: bool = IS_TEST,
):
    agent = AgentBuilder(
        repo=repo,
        model_config=model_config,
        response_format=response_format,
    ).build()

    message = {"messages": HumanMessage(content=prompt)}

    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(uuid4()),
            "step_limit": 10,
        },
        "recursion_limit": 50,
    }

    response = await agent.ainvoke(message, config=config)

    if debug:
        for message in response["messages"]:
            if isinstance(message, ToolMessage):
                message.pretty_print()

    if response_format:
        return response["structured_response"]

    return response["messages"][-1].content
