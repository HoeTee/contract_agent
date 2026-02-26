from __future__ import annotations # no quotes are needed for type hints

import json
import traceback # help show where the error happended
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional

import sys
import os
# Add parent directory to path for logger import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger.logger import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


class MinimalMCPClient:
    """
    Minimal MCP client that:
    - connects to a server over stdio
    - exposes MCP tools in OpenAI Chat Completions format
    - executes tool calls and returns Chat Completions tool messages
    """

    def __init__(self, server_script_path: str = "") -> None:
        self.server_script_path = server_script_path
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.tools: List[Dict[str, Any]] = []
        self.logger = logger

    async def connect(
        self,
        server_script_path: str = None,
    ) -> None:
        server_script_path = server_script_path or self.server_script_path
        if not server_script_path:
            raise ValueError("No server_script_path provided")
        try: 
            is_http = server_script_path.startswith(".http")
            is_https = server_script_path.startswith(".https")
            is_python = server_script_path.endswith(".py")
            is_js = server_script_path.endswith(".js")

            if not (is_http or is_https or is_python or is_js):
                raise ValueError("Server path/script must be a .http, .https, .py, or .js file")
            
            elif is_http or is_https:
                sse_transport = await self.exit_stack.enter_async_context(
                    sse_client(server_script_path)
                )
                stdio, write = sse_transport
                self.session = await self.exit_stack.enter_async_context(
                    ClientSession(stdio, write)
                )
                await self.session.initialize()

                self.tools = await self.list_tools_openai()
                self.logger.info(f"Connected to remote server. Tools: {[t['function']['name'] for t in self.tools]}")

            elif is_python or is_js:
                command = "python" if is_python else "node"
                server_params = StdioServerParameters(
                    command=command,
                    args=[server_script_path],
                    env=None,
                )
                stdio_transport = await self.exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                stdio, write = stdio_transport
                self.session = await self.exit_stack.enter_async_context(
                    ClientSession(stdio, write)
                )
                await self.session.initialize()

                self.tools = await self.list_tools_openai()
                self.logger.info(f"Connected to remote server. Tools: {[t['function']['name'] for t in self.tools]}")
        
        except Exception as e:
            self.logger.error(f"Error connecting to MCP server: {e}")
            traceback.print_exc() 
            raise


    async def list_tools_openai(
        self
    ) -> List[Dict[str, Any]]:
        if not self.session:
            raise RuntimeError("Client not connected")
        response = await self.session.list_tools()
        tool_schema = [
            {
                "type": "function",
                "function": {
                    "name": tool.name, # function name
                    "description": tool.description, # doc string
                    "parameters": tool.inputSchema, # MyModel.model_json_schema()
                },
            }
            for tool in response.tools
        ]
        return tool_schema


    async def call_tool(
        self,
        name: str,
        args: Dict[str, Any]
    ) -> str:
        """Call tool and return text result as string."""
        if not self.session:
            raise RuntimeError("Client not connected")
        result = await self.session.call_tool(name, args)
        # Extract .text from TextContent objects
        if hasattr(result, 'content') and isinstance(result.content, list):
            texts = []
            for item in result.content:
                if hasattr(item, 'text'):
                    texts.append(item.text)
                elif isinstance(item, dict) and 'text' in item:
                    texts.append(item['text'])
                else:
                    texts.append(str(item))
            return "\n".join(texts)
        return str(result)

    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Return cached tools list in OpenAI format."""
        return self.tools


    def serialize_content(
        self, 
        content: Any
    ) -> Any:
        """
        serialize_content performs purely in-memory data transformation, 
        which does not involve any I/O operations like network requests, 
        file reading, or database queries that would require waiting (await). 
        """
        if content is None or isinstance(content, str):
            return content
        if isinstance(content, list):
            return [
                c.model_dump() if hasattr(c, "model_dump") else
                c.text if hasattr(c, "text") else
                str(c)
                for c in content
            ]
        if hasattr(content, "model_dump"):
            return content.model_dump()
        return str(content)


    async def tool_message_from_call(
        self, 
        tool_call: Any
    ) -> Dict[str, Any]:
        """
        Accepts a Chat Completions tool_call object and returns a
        {"role":"tool", ...} message with serialized content.
        """
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments or "{}")
        content = await self.call_tool(name, args)
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": content,
        }

    async def cleanup(
        self
    ) -> None:
        try:
            await self.exit_stack.aclose()
            self.logger.info("Disconnected from MCP server")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
            traceback.print_exc()


    async def log_conversation(self):
        """
        Chat Completions-style messages expected (examples):
        {"role":"user","content":"..."}
        {"role":"assistant","content":"..."}
        {"role":"assistant","content":"...", "tool_calls":[{"id":"...","type":"function","function":{"name":"...","arguments":"{...}"}}]}
        {"role":"tool","tool_call_id":"...","content":"..."}
        """
        # create a directory named "conversation" to stores all conversations
        os.makedirs("conversations", exist_ok=True)

        serializable_conversation = []

        for message in self.messages:
            try:
                role = message.get("role")
                out = {"role": role}

                # ---- content (string only, as per Chat Completions) ----
                if "content" in message:
                    c = message["content"]
                    if c is None or isinstance(c, str):
                        out["content"] = c
                    else:
                        # if you accidentally stored non-string content, stringify it
                        out["content"] = str(c)

                # ---- assistant tool_calls ----
                if role == "assistant" and "tool_calls" in message:
                    tool_calls = message["tool_calls"] or []
                    out_tool_calls = []
                    for tc in tool_calls:
                        # tolerate both dict tool_calls and SDK objects
                        if hasattr(tc, "model_dump"):
                            tc = tc.model_dump()
                        elif hasattr(tc, "to_dict"):
                            tc = tc.to_dict()
                        elif hasattr(tc, "dict"):
                            tc = tc.dict()

                        out_tool_calls.append(
                            {
                                "id": tc.get("id"),
                                "type": tc.get("type", "function"),
                                "function": {
                                    "name": (tc.get("function") or {}).get("name"),
                                    "arguments": (tc.get("function") or {}).get("arguments"),
                                },
                            }
                        )
                    out["tool_calls"] = out_tool_calls

                # ---- tool result message ----
                if role == "tool":
                    out["tool_call_id"] = message.get("tool_call_id")

                # keep other fields if you stored any (safe stringify)
                for k, v in message.items():
                    if k in out or k in ("role", "content", "tool_calls", "tool_call_id"):
                        continue
                    out[k] = v if isinstance(v, (str, int, float, bool)) or v is None else str(v)

                serializable_conversation.append(out)

            except Exception as e:
                self.logger.error(f"Error processing message: {str(e)}")
                self.logger.debug(f"Message content: {message}")
                raise

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join("conversations", f"conversation_{timestamp}.json")

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(serializable_conversation, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Error writing conversation to file: {str(e)}")
            self.logger.debug(f"Serializable conversation: {serializable_conversation}")
            raise