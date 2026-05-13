"""
ContractReviewWorkflow — orchestrates the full 6-phase contract review.

Phases:
  1. Ingest criteria + contract → markdown
  2. Build PageIndex tree from contract
  3. Planner designs tasks from criteria
  4. Orchestrator executes sub-agents with PageIndex retrieval + reflection
  5. Summarizer compiles final report
  6. Generate MD, DOCX, and PDF reports
"""
import inspect
import json
import os
import re
import time
from typing import Any, Awaitable, Callable

from config import (
    MCP_SERVER_PATH,
    get_default_institutional_rag_enabled,
    get_default_retrieval_mode,
    get_default_web_search_enabled,
    get_retrieval_mode,
)
from main_workflow.workflow_logger import WorkflowLogger
from agents.base_agent import Settings
from agents.planner import PlannerAgent
from agents.orchestrator import OrchestratorAgent
from agents.summarizer import SummarizerAgent
from mcp_service.mcp_client.mcp_minimal import MinimalMCPClient
from main_workflow.report_renderer import build_review_items, flatten_issues, render_report_markdown


class ContractReviewWorkflow:
    """High-level coordinator for one contract review run.

    This module is intentionally the workflow glue layer. It owns phase order,
    progress emission, logging, and final result assembly, while the detailed
    work for parsing, retrieval, review, and summarization stays in helper
    agents and MCP tools.
    """

    def __init__(self, server_script_path: str = MCP_SERVER_PATH):
        self.mcp_client = MinimalMCPClient(server_script_path)
        self.logger = WorkflowLogger()
        self.settings = Settings()

    async def run(
        self,
        contract_path: str,
        criteria_path: str,
        retrieval_mode: str | None = None,
        web_search_enabled: bool | None = None,
        institutional_rag_enabled: bool | None = None,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full review workflow.
        Returns: structured review data for the API layer.
        """
        retrieval_mode = retrieval_mode or get_default_retrieval_mode()
        web_search_enabled = get_default_web_search_enabled() if web_search_enabled is None else web_search_enabled
        institutional_rag_enabled = (
            get_default_institutional_rag_enabled()
            if institutional_rag_enabled is None
            else institutional_rag_enabled
        )
        mode_label = get_retrieval_mode(retrieval_mode)
        workflow_start = time.time()
        print("=" * 60)
        print("Contract Review Workflow")
        print("=" * 60)
        print(f"Selected retrieval mode: {retrieval_mode} ({mode_label})")
        print(f"Web search enabled: {web_search_enabled}")
        print(f"Institutional RAG enabled: {institutional_rag_enabled}")

        # Initialize MCP client
        await self.mcp_client.connect()

        try:
            # Phase 1: Ingest files
            await self._emit_progress(progress_callback, "ingesting", "Parsing contract and criteria files")
            criteria_md, contract_md = await self._phase_ingest(contract_path, criteria_path)

            # Phase 2: Build index / tree
            if retrieval_mode == "llamaindex":
                await self._emit_progress(progress_callback, "building_index", "Building temporary LlamaIndex contract index")
                await self._phase_build_llamaindex(contract_md)
                tree_json = None
            elif retrieval_mode == "pageindex":
                await self._emit_progress(progress_callback, "building_tree", "Building the contract structure tree")
                tree_json = await self._phase_build_tree(contract_md)
            else:
                tree_json = await self._phase_build_tree(contract_md)

            # Phase 3: Plan tasks
            await self._emit_progress(progress_callback, "planning", "Extracting review criteria")
            criteria_list = await self._phase_plan(criteria_md)

            # Phase 4: Execute + Reflect
            print(f"\n  Search mode: {mode_label}")
            await self._emit_progress(
                progress_callback,
                "reviewing",
                f"Reviewing {len(criteria_list)} criteria with the agent workflow",
            )
            results = await self._phase_execute(
                criteria_list,
                tree_json,
                retrieval_mode,
                web_search_enabled,
                institutional_rag_enabled,
            )
            debug_results_path = os.path.join("logs", "workflow", "last_results.json")
            os.makedirs(os.path.dirname(debug_results_path), exist_ok=True)
            with open(debug_results_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            # Phase 5: Summarize
            await self._emit_progress(progress_callback, "summarizing", "Compiling the final report")
            summary_sections = await self._phase_summarize(results)
            report_text = render_report_markdown(summary_sections, results)

            token_stats = self._collect_token_stats(results)
            total_tokens = token_stats["total"]
            report_text = self._append_report_metadata(
                report_text,
                criteria_list,
                results,
                mode_label,
                token_stats,
            )

            # Phase 6: Generate reports (MD + DOCX + PDF)
            elapsed = round(time.time() - workflow_start, 1)
            await self._emit_progress(progress_callback, "generating_report", "Generating report artifacts")
            report_paths = await self._phase_generate_report(
                report_text, contract_path,
                elapsed_seconds=elapsed, results=results,
            )
            issues = flatten_issues(results)
            review_items = build_review_items(results)

            # Save workflow log
            log_path = self.logger.save()
            elapsed = round(time.time() - workflow_start, 1)
            self._print_completion_summary(elapsed, token_stats, report_paths, log_path)

            await self._emit_progress(progress_callback, "completed", "Review completed")

            return {
                "issues": issues,
                "review_items": review_items,
                "report_md": report_paths.get("md"),
                "report_docx": report_paths.get("docx"),
                "report_pdf": report_paths.get("pdf"),
                "report_text": report_text,
                "criteria_count": len(criteria_list),
                "total_tokens": total_tokens,
                "retrieval_mode": retrieval_mode,
                "web_search_enabled": web_search_enabled,
                "institutional_rag_enabled": institutional_rag_enabled,
                "workflow_log": log_path,
            }

        finally:
            await self.mcp_client.cleanup()

    # ==================== Phases ====================

    async def _emit_progress(
        self,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
        stage: str,
        message: str,
    ) -> None:
        """Forward a lightweight stage update to the optional UI callback."""
        if progress_callback is None:
            return

        update = {"stage": stage, "message": message}
        maybe_awaitable = progress_callback(update)
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable

    async def _phase_ingest(self, contract_path: str, criteria_path: str) -> tuple[str, str]:
        """Phase 1: Ingest contract + criteria DOCX files."""
        print("\n[Phase 1] Ingesting files...")
        criteria_md = await self._ingest_markdown_file(criteria_path, "criteria")
        contract_md = await self._ingest_markdown_file(contract_path, "contract")

        print(f"  Criteria: {len(criteria_md)} chars")
        print(f"  Contract: {len(contract_md)} chars")
        return criteria_md, contract_md

    async def _ingest_markdown_file(self, file_path: str, input_label: str) -> str:
        """Run the shared ingestion tool and strip its response wrapper.

        The MCP tool returns:
            File 'name' ingested. Content:
            <markdown body>
        Downstream phases only need the markdown body, so this helper keeps the
        call, logging, and wrapper stripping in one place.
        """
        start = time.time()
        tool_result = await self.mcp_client.call_tool(
            "ingest_file", {"file_path": file_path}
        )
        self.logger.log(
            phase="Ingestion", sender="Workflow", receiver="MCP:ingest_file",
            action=f"ingest_file({input_label})",
            input_summary=os.path.basename(file_path),
            output_summary=f"{len(tool_result)} chars",
            duration=round(time.time() - start, 2)
        )
        return tool_result.split("\n\n", 1)[-1] if "\n\n" in tool_result else tool_result

    async def _phase_build_tree(self, contract_md: str) -> str:
        """Phase 2: Build PageIndex tree from contract markdown."""
        print("\n[Phase 2] Building PageIndex tree...")
        start = time.time()

        tree_json = await self.mcp_client.call_tool(
            "build_pageindex_tree", {"markdown_content": contract_md}
        )

        self.logger.log(
            phase="Tree Building", sender="Workflow", receiver="MCP:build_pageindex_tree",
            action="build_pageindex_tree",
            input_summary=f"{len(contract_md)} chars markdown",
            output_summary=f"{len(tree_json)} chars tree JSON",
            duration=round(time.time() - start, 2)
        )

        # Validate tree
        if tree_json.startswith("Error"):
            raise RuntimeError(f"Tree building failed: {tree_json}")
        try:
            tree_obj = json.loads(tree_json)
            has_structure = "structure" in tree_obj or "nodes" in tree_obj
            if not has_structure:
                print(f"  WARNING: Tree has no 'structure'/'nodes' key. Keys: {list(tree_obj.keys())}")
        except json.JSONDecodeError:
            raise RuntimeError(f"Tree JSON is invalid (len={len(tree_json)}): {tree_json[:200]}")

        print(f"  Tree: {len(tree_json)} chars (built in {round(time.time()-start,1)}s)")
        return tree_json

    async def _phase_build_llamaindex(self, contract_md: str) -> str:
        """Phase 2 (LlamaIndex mode): Build a temporary contract vector index."""
        print("\n[Phase 2] Building temporary LlamaIndex contract index...")
        start = time.time()

        result = await self.mcp_client.call_tool(
            "llamaindex_build_index", {"markdown_content": contract_md}
        )

        self.logger.log(
            phase="Index Building", sender="Workflow", receiver="MCP:llamaindex_build_index",
            action="llamaindex_build_index",
            input_summary=f"{len(contract_md)} chars markdown",
            output_summary=result,
            duration=round(time.time() - start, 2)
        )

        parsed = json.loads(result)
        if parsed.get("error"):
            raise RuntimeError(f"LlamaIndex index build failed: {parsed['error']}")

        print(f"  Temporary index built in {round(time.time()-start,1)}s: {result[:200]}")
        return result

    async def _phase_plan(self, criteria_md: str) -> list[dict]:
        """Phase 3: Planner designs structured tasks from criteria."""
        print("\n[Phase 3] Planning tasks...")
        start = time.time()

        planner = PlannerAgent(settings=self.settings)
        plan_result = await planner.design_tasks(criteria_md)

        criteria_list = plan_result.get("criteria", []) 
        self._planner_tokens = planner.token_usage.get("total_tokens", 0)
        self.logger.log(
            phase="Planning", sender="Workflow", receiver="Planner",
            action="design_tasks",
            input_summary=f"{len(criteria_md)} chars criteria",
            output_summary=f"{len(criteria_list)} criteria extracted",
            tokens=self._planner_tokens,
            duration=round(time.time() - start, 2)
        )

        print(f"  Criteria: {len(criteria_list)} tasks")
        for c in criteria_list:
            print(f"    {c['id']}: {c['criterion'][:50]}...")
        return criteria_list

    async def _phase_execute(
        self,
        criteria_list: list[dict],
        tree_json: str | None,
        retrieval_mode: str,
        web_search_enabled: bool,
        institutional_rag_enabled: bool,
    ) -> list[dict]:
        """Phase 4: Orchestrator runs sub-agents with PageIndex retrieval + reflection."""
        print(f"\n[Phase 4] Executing {len(criteria_list)} criteria reviews...")
        start = time.time()

        orchestrator = OrchestratorAgent(
            mcp_client=self.mcp_client,
            logger=self.logger,
            settings=self.settings,
            retrieval_mode=retrieval_mode,
            web_search_enabled=web_search_enabled,
            institutional_rag_enabled=institutional_rag_enabled,
        )
        results = await orchestrator.execute_criteria(criteria_list, tree_json)
        self._retrieval_tokens = getattr(orchestrator, 'retrieval_tokens', 0)

        self.logger.log(
            phase="Execution", sender="Orchestrator", receiver="Workflow",
            action="execute_criteria_complete",
            input_summary=f"{len(criteria_list)} criteria",
            output_summary=f"{len(results)} results",
            duration=round(time.time() - start, 2)
        )

        print(f"  Completed: {len(results)} reviews")
        return results

    async def _phase_summarize(self, results: list[dict]) -> dict[str, str]:
        """Phase 5: Summarizer produces overview and priority advice sections."""
        print("\n[Phase 5] Summarizing...")
        start = time.time()

        summarizer = SummarizerAgent(settings=self.settings)
        summary_sections = await summarizer.compile_report(results)

        self._summarizer_tokens = summarizer.token_usage.get("total_tokens", 0)
        self.logger.log(
            phase="Summarization", sender="Summarizer", receiver="Workflow",
            action="compile_report",
            input_summary=f"{len(results)} criterion results",
            output_summary=f"{len(json.dumps(summary_sections, ensure_ascii=False))} chars summary",
            tokens=self._summarizer_tokens,
            duration=round(time.time() - start, 2)
        )

        print(f"  Summary sections: {len(summary_sections)}")
        return summary_sections

    def _build_checklist(self, criteria_list: list[dict], results: list[dict]) -> str:
        """Build a markdown checklist showing which extracted criteria were reviewed."""
        lines = [
            "\n\n---\n",
            "## 附：审查标准覆盖核查表\n",
            "| 序号 | 审查内容 | 审查状态 |",
            "|------|---------|---------|",
        ]
        total_items = 0
        checked_items = 0

        # Group criteria by section (preserving insertion order)
        grouped_criteria = {}
        for c in criteria_list:
            s = c.get("section", "其他")
            if s not in grouped_criteria:
                grouped_criteria[s] = []
            grouped_criteria[s].append(c)

        import re
        major_idx = 1
        for section_name, items in grouped_criteria.items():
            # Add section header in the table
            lines.append(f"| **—** | **【{section_name}】** | **—** |")
            
            minor_idx = 1
            for c in items:
                cid = c["id"]
                result = next((r for r in results if r.get("criterion_id") == cid), None)
                is_reviewed = result is not None and result.get("status") != "ERROR"
                
                status = "✅" if is_reviewed else "❌"
                display_c = re.sub(r'^\d+[\.、]\s*', '', c['criterion'])
                lines.append(f"| **{major_idx}.{minor_idx}** | **{display_c[:60]}** | **{status}** |")
                
                total_items += 1
                if is_reviewed:
                    checked_items += 1
                        
                minor_idx += 1
            major_idx += 1

        lines.append(f"\n**覆盖率：{checked_items}/{total_items}（{checked_items*100//total_items if total_items else 0}%）**\n")
        return "\n".join(lines)

    def _collect_token_stats(self, results: list[dict]) -> dict[str, int]:
        """Aggregate token counters collected across workflow phases."""
        planner_tokens = getattr(self, "_planner_tokens", 0)
        retrieval_tokens = getattr(self, "_retrieval_tokens", 0)
        summarizer_tokens = getattr(self, "_summarizer_tokens", 0)
        execute_tokens = sum(result.get("tokens", 0) for result in results)
        return {
            "planner": planner_tokens,
            "retrieval": retrieval_tokens,
            "execute": execute_tokens,
            "summarizer": summarizer_tokens,
            "total": planner_tokens + retrieval_tokens + execute_tokens + summarizer_tokens,
        }

    def _append_report_metadata(
        self,
        report_text: str,
        criteria_list: list[dict],
        results: list[dict],
        mode_label: str,
        token_stats: dict[str, int],
    ) -> str:
        """Append workflow-generated metadata sections to the final markdown report."""
        report_text += self._build_checklist(criteria_list, results)
        report_text += self._build_token_stats_section(mode_label, token_stats)
        return report_text

    def _build_token_stats_section(self, mode_label: str, token_stats: dict[str, int]) -> str:
        """Render the token usage appendix added to the exported report."""
        return (
            f"\n\n---\n\n"
            f"## 附：Token 消耗统计\n\n"
            f"| 阶段 | Token 消耗 |\n"
            f"|------|----------|\n"
            f"| 规划（Planner） | {token_stats['planner']:,} |\n"
            f"| 检索（{mode_label}） | {token_stats['retrieval']:,} |\n"
            f"| 审查（Sub-Agents + Reflectors） | {token_stats['execute']:,} |\n"
            f"| 汇总（Summarizer） | {token_stats['summarizer']:,} |\n"
            f"| **合计** | **{token_stats['total']:,}** |\n"
        )

    async def _phase_generate_report(
        self, report_text: str, contract_path: str,
        elapsed_seconds: float = None, results: list = None,
    ) -> dict[str, str | None]:
        """Phase 6: Generate MD, DOCX, and PDF reports."""
        print("\n[Phase 6] Generating reports (MD + DOCX + PDF)...")
        start = time.time()

        contract_name = os.path.splitext(os.path.basename(contract_path))[0]

        # Build MCP tool arguments
        tool_args = {
            "content_json": report_text,
            "contract_name": contract_name,
            "elapsed_seconds": elapsed_seconds,
            "contract_path": contract_path,
        }

        # Pass structured results as JSON for DOCX comment generation
        if results:
            tool_args["results_json"] = json.dumps(results, ensure_ascii=False)

        # Generate all three report formats via MCP tool
        result = await self.mcp_client.call_tool(
            "generate_final_report", tool_args
        )

        self.logger.log(
            phase="Report", sender="Workflow", receiver="MCP:generate_report",
            action="generate_final_report",
            input_summary=f"{len(report_text)} chars",
            output_summary=result,
            duration=round(time.time() - start, 2)
        )

        print(f"  {result}")
        return self._parse_report_paths(result)

    def _print_completion_summary(
        self,
        elapsed_seconds: float,
        token_stats: dict[str, int],
        report_paths: dict[str, str | None],
        log_path: str,
    ) -> None:
        """Print the compact end-of-run summary used by local/CLI execution."""
        mins, secs = divmod(int(elapsed_seconds), 60)
        print(f"\n{'=' * 60}")
        print(f"Workflow complete! Total time: {mins}m {secs}s")
        print(
            "Total tokens: "
            f"{token_stats['total']:,} "
            f"(Planner: {token_stats['planner']:,} | "
            f"Retrieval: {token_stats['retrieval']:,} | "
            f"Execute: {token_stats['execute']:,} | "
            f"Summarizer: {token_stats['summarizer']:,})"
        )
        print(f"Report: {report_paths}")
        print(f"Log: {log_path}")
        print(f"{'=' * 60}")

    def _parse_report_paths(self, tool_output: str) -> dict[str, str | None]:
        """Parse plain-text MCP output into typed report paths.

        The report generator returns a human-readable block rather than JSON, so
        this helper normalizes `MD/DOCX/PDF: ...` lines before the API layer
        consumes them.
        """
        paths: dict[str, str | None] = {"md": None, "docx": None, "pdf": None}

        for raw_line in tool_output.splitlines():
            line = raw_line.strip()
            match = re.match(r"^(MD|DOCX|PDF):\s*(.+)$", line, flags=re.IGNORECASE)
            if not match:
                continue

            fmt = match.group(1).lower()
            value = match.group(2).strip()
            paths[fmt] = None if value.upper() == "FAILED" else value

        return paths

