"""
OrchestratorAgent — dispatches sub-agents per criterion with PageIndex retrieval + reflection.
"""
import asyncio
import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import MAX_REFLECTION_ROUNDS
from agent.agent import Agent
from agents.reflector import ReflectorAgent
from agents.prompts.cn_prompts import SUB_AGENT_BASE_PROMPT


class OrchestratorAgent:
    """Coordinates per-criterion sub-agents with PageIndex retrieval and reflection."""

    def __init__(self, mcp_client, logger=None, settings=None):
        self.mcp_client = mcp_client
        self.logger = logger
        self.settings = settings
        self.tools = None

    async def _get_tools(self) -> list[str]:
        """Cache MCP tools list."""
        if self.tools is None:
            self.tools = await self.mcp_client.get_available_tools()
        return self.tools

    async def execute_single_criterion(self, criterion: dict, tree_json: str) -> dict:
        """
        Review a single criterion:
        1. Call pageindex_search to get relevant contract sections
        2. Create sub-agent with context
        3. Run reflector loop until PASS or max rounds
        """
        cid = criterion["id"]
        criterion_text = criterion["criterion"]
        check_points = criterion.get("check_points", [])
        check_points_text = "\n".join(f"- {cp}" for cp in check_points)
        start = time.time()

        # Step 1: Retrieve relevant contract sections via PageIndex
        print(f"[Orchestrator] {cid}: Searching contract via PageIndex...")
        search_query = f"{criterion_text}\n检查要点：{check_points_text}"
        search_result = await self.mcp_client.call_tool(
            "pageindex_search",
            {"query": search_query, "tree_json": tree_json}
        )
        context = search_result if search_result else "未找到相关内容"

        if self.logger:
            self.logger.log(
                phase="Execute", sender="Orchestrator", receiver="MCP:pageindex_search",
                action=f"pageindex_search({cid})",
                input_summary=criterion_text,
                output_summary=f"{len(context)} chars retrieved",
                duration=round(time.time() - start, 2)
            )

        # Step 2: Create sub-agent with retrieved context
        tools = await self._get_tools()
        sub_agent = Agent(
            system_prompt=SUB_AGENT_BASE_PROMPT,
            name=f"SubAgent_{cid}",
            mcp_client=self.mcp_client,
            tools=tools,
            settings=self.settings,
        )

        task_prompt = (
            f"审查标准：{criterion_text}\n"
            f"检查要点：\n{check_points_text}\n\n"
            f"以下是合同中与此标准相关的内容：\n\n{context}"
        )
        opinion = await sub_agent.chat(task_prompt)

        if self.logger:
            self.logger.log(
                phase="Execute", sender=f"SubAgent_{cid}", receiver="LLM",
                action=f"review({cid})",
                input_summary=f"criterion + {len(context)} chars context",
                output_summary=opinion,
                tokens=sub_agent.token_usage.get("total_tokens", 0),
                duration=round(time.time() - start, 2)
            )

        # If sub-agent found no issues at all across all check points, short-circuit
        if "[ALL_COMPLIANT]" in opinion or not opinion.strip():
            print(f"[Orchestrator] {cid}: All check points compliant, skipping reflection.")
            return {
                "criterion_id": cid,
                "criterion": criterion_text,
                "section": criterion.get("section", "其他"),
                "review_output": "",
                "status": "COMPLIANT",
                "reflection_rounds": 0,
                "tokens": sub_agent.token_usage.get("total_tokens", 0),
            }

        # Step 3: Reflection loop
        reflector = ReflectorAgent(settings=self.settings)
        for round_num in range(MAX_REFLECTION_ROUNDS):
            review = await reflector.review(
                agent_output=opinion,
                evaluation_criteria=f"审查标准：{criterion_text}\n检查要点：\n{check_points_text}"
            )

            if self.logger:
                status = review.get("status", "UNKNOWN")
                self.logger.log(
                    phase="Reflect", sender="Reflector", receiver=f"SubAgent_{cid}",
                    action=f"reflect({cid}, round={round_num+1})",
                    input_summary=opinion,
                    output_summary=f"{status}: {review.get('feedback', '')}",
                    tokens=reflector.token_usage.get("total_tokens", 0),
                    duration=round(time.time() - start, 2)
                )

            if review.get("status") == "PASS":
                print(f"[Orchestrator] {cid}: PASS after {round_num+1} round(s)")
                break

            # Feed back to sub-agent for refinement
            print(f"[Orchestrator] {cid}: REJECT round {round_num+1}, refining...")
            opinion = await sub_agent.chat(
                f"请根据以下质量审查反馈，补充和完善你的审查结果：\n\n{review.get('feedback', '')}"
            )
        else:
            print(f"[Orchestrator] {cid}: Max {MAX_REFLECTION_ROUNDS} rounds reached")

        # Aggregate tokens: sub-agent + reflector
        total_tokens = sub_agent.token_usage.get("total_tokens", 0) + reflector.token_usage.get("total_tokens", 0)

        is_compliant = "[ALL_COMPLIANT]" in opinion
        return {
            "criterion_id": cid,
            "criterion": criterion_text,
            "section": criterion.get("section", "其他"),
            "review_output": "" if is_compliant else opinion,
            "status": "COMPLIANT" if is_compliant else "ISSUES_FOUND",
            "reflection_rounds": round_num + 1 if 'round_num' in dir() else 0,
            "tokens": total_tokens,
        }

    async def execute_criteria(self, criteria_list: list[dict], tree_json: str) -> list[dict]:
        """Execute all criteria concurrently."""
        tasks = [
            self.execute_single_criterion(c, tree_json)
            for c in criteria_list
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"[Orchestrator] Error on criterion {criteria_list[i]['id']}: {r}")
                final.append({
                    "criterion_id": criteria_list[i]["id"],
                    "criterion": criteria_list[i]["criterion"],
                    "section": criteria_list[i].get("section", "其他"),
                    "review_output": "",  # Empty string so it gets excluded from report
                    "status": "ERROR",
                    "reflection_rounds": 0,
                    "tokens": 0,
                })
            else:
                final.append(r)

        total_tokens = sum(r.get("tokens", 0) for r in final)
        print(f"  Completed: {len(final)} reviews, Total tokens: {total_tokens:,}")
        return final
