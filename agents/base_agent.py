"""
Base Agent class — handles LLM communication, tool calling, context
management, token tracking, and conversation logging.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from openai import AsyncOpenAI
from agents.agent_logger import log_conversation
import json
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    api_key: str = Field(..., alias="API_KEY")
    base_url: str = Field(..., alias="BASE_URL")
    model: str = Field(..., alias="LLM_NAME")
    temperature: float = Field(0.0, alias="TEMPERATURE")
    top_p: float = Field(0.01, alias="TOP_P")
    seed: int = Field(42, alias="SEED")


class Agent:

    MAX_TOOL_CALLS = 30
    MAX_CONTEXT_TOKENS = 100000
    MAX_RESULT_TOKENS = 5000

    def __init__(
        self,
        system_prompt: str = "",
        name: str = "Agent",
        mcp_client=None,
        tools=None,
        settings: Settings = None,
        debug: bool = False,
    ) -> None:
        self.settings = settings or Settings()
        self.client = AsyncOpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
        )
        self.name = name
        self.mcp_client = mcp_client
        self.tools = tools or (mcp_client.tools if mcp_client else [])
        self.messages: list = []
        self.debug = debug

        # Token tracking
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.tool_call_count = 0

        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    # ==================== Logging ====================

    def _log(self, message: str):
        if self.debug:
            print(f"[{self.name}] {message}")

    def _estimate_tokens(self, text: str) -> int:
        return int(len(text) * 0.3)

    # ==================== Context ====================

    def _check_context_limits(self):
        total_chars = sum(len(str(msg.get("content", ""))) for msg in self.messages)
        estimated = self._estimate_tokens(str(total_chars))
        self._log(f"Pre-request: {len(self.messages)} messages, ~{estimated} tokens")
        if estimated > self.MAX_CONTEXT_TOKENS:
            print(f"[{self.name}] ⚠️ Context tokens ({estimated}) approaching limit!")

    def _truncate_text(self, text: str, max_tokens: int = None) -> str:
        if max_tokens is None:
            max_tokens = self.MAX_RESULT_TOKENS
        estimated = self._estimate_tokens(text)
        if estimated <= max_tokens:
            return text
        max_chars = int(max_tokens / 0.3)
        return text[:max_chars] + "\n\n[... Content truncated ...]"

    # ==================== Token Tracking ====================

    def _update_token_usage(self, usage):
        if usage:
            self.token_usage["prompt_tokens"] += usage.prompt_tokens
            self.token_usage["completion_tokens"] += usage.completion_tokens
            self.token_usage["total_tokens"] += usage.total_tokens

    def get_token_usage(self) -> dict:
        return self.token_usage.copy()

    # ==================== Tool Calls ====================

    def _parse_tool_arguments(self, args_str: str, function_name: str) -> dict | None:
        try:
            return json.loads(args_str)
        except json.JSONDecodeError:
            self._log(f"⚠️ JSON parse error for '{function_name}'")
            start = args_str.find("{")
            end = args_str.rfind("}") + 1
            if start != -1 and end != 0:
                try:
                    return json.loads(args_str[start:end])
                except json.JSONDecodeError:
                    pass
            print(f"[{self.name}] ✗ Failed to parse tool arguments for {function_name}")
            return None

    async def _execute_tool(self, tool_call) -> str:
        function_name = tool_call.function.name
        self._log(f"→ Calling tool: {function_name}")

        args_dict = self._parse_tool_arguments(tool_call.function.arguments, function_name)
        if args_dict is None:
            return "Failed to parse tool arguments."

        if self.mcp_client:
            tool_msg = await self.mcp_client.tool_message_from_call(tool_call)
            result = tool_msg["content"]
        else:
            return f"No MCP client for tool {function_name}"

        result_str = str(result)
        estimated = self._estimate_tokens(result_str)
        if estimated > 10000:
            result_str = self._truncate_text(result_str)
            self._log(f"← Tool '{function_name}': ~{estimated} tokens (truncated)")
        else:
            self._log(f"← Tool '{function_name}': ~{estimated} tokens")
        return result_str

    async def _process_tool_calls(self, tool_calls):
        self.tool_call_count += len(tool_calls)
        self._log(f"Processing {len(tool_calls)} tool calls (total: {self.tool_call_count})")

        if self.tool_call_count > self.MAX_TOOL_CALLS:
            print(f"[{self.name}] ⚠️ Max tool calls ({self.MAX_TOOL_CALLS}) reached. Aborting task and marking review invalid.")
            raise RuntimeError(f"[{self.name}] Reached maximum tool calls ({self.MAX_TOOL_CALLS}) without completing the task. The review is considered invalid and has been excluded.")

        for tool_call in tool_calls:
            result = await self._execute_tool(tool_call)
            self.messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result
            })
        log_conversation(self.name, self.messages)
        return None

    # ==================== Main Loop ====================

    async def chat(self, message="") -> str:
        if message:
            self.messages.append({"role": "user", "content": message})
            log_conversation(self.name, self.messages)

        result = await self.execute()
        if result is not None:
            self.messages.append({"role": "assistant", "content": result})
            log_conversation(self.name, self.messages)
        else:
            raise ValueError("No final assistant content returned.")
        return result

    async def execute(self) -> str:
        while True:
            self._check_context_limits()

            completion = await self.client.chat.completions.create(
                model=self.settings.model,
                temperature=self.settings.temperature,
                top_p=self.settings.top_p,
                seed=self.settings.seed,
                messages=self.messages,
                tools=self.tools if self.tools else None,
                tool_choice="auto" if self.tools else None
            )

            response_message = completion.choices[0].message
            self._update_token_usage(completion.usage)

            if response_message.tool_calls:
                self.messages.append(response_message.model_dump(exclude_unset=True))
                log_conversation(self.name, self.messages)
                forced = await self._process_tool_calls(response_message.tool_calls)
                if forced:
                    self.messages.pop()  # Remove unresolved tool_calls message preventing API errors
                    return forced
            else:
                return response_message.content

