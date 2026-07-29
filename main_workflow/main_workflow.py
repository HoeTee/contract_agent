"""
ContractReviewWorkflow orchestrates one annotated-DOCX contract review run.

Phases:
  1. Ingest criteria + contract to markdown
  2. Build a temporary LlamaIndex contract index from DOCX XML anchors
  3. Planner extracts review criteria
  4. Orchestrator executes criterion reviews with retrieval + reflection
  5. Summarizer creates a compact summary comment
  6. Generate the annotated original-contract DOCX
"""
import inspect
import json
import os
import time
from typing import Any, Awaitable, Callable

from config import (
    ENABLE_WORKFLOW_LOGS,
    MCP_SERVER_PATH,
)
from loggers.workflow_logger import WorkflowLogger, save_results_json, save_run_summary_json
from agents.base_agent import Settings
from agents.planner import PlannerAgent
from agents.orchestrator import OrchestratorAgent
from agents.summarizer import SummarizerAgent
from mcp_service.mcp_client.mcp_minimal import MinimalMCPClient
from endpoints.runtime.errors import classify_model_call_error


class ContractReviewWorkflow:
    """High-level coordinator for one contract review run.

    This module is intentionally the workflow glue layer. It owns phase order,
    progress emission, logging, and final result assembly, while the detailed
    work for parsing, retrieval, review, and summarization stays in helper
    agents and MCP tools.
    """

    def __init__(
        self,
        server_script_path: str = MCP_SERVER_PATH,
        workflow_log_dir: str | None = None,
        conversation_log_dir: str | None = None,
        mcp_log_file: str | None = None,
        api_events_path: str | None = None,
    ):
        self.mcp_client = MinimalMCPClient(server_script_path, log_file=mcp_log_file)
        self.logger = WorkflowLogger(log_dir=workflow_log_dir)
        self.workflow_log_dir = workflow_log_dir
        self.conversation_log_dir = conversation_log_dir
        self.api_events_path = api_events_path
        self.settings = Settings()

    async def run(
        self,
        contract_path: str,
        criteria_path: str,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
        output_dir: str | None = None,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full review workflow.
        Returns: structured review data for the API layer.
        """
        if not output_dir and not output_path:
            raise ValueError(
                "output_dir or output_path is required for report generation."
            )

        workflow_start = time.time()
        print("=" * 60)
        print("Contract Review Workflow Started")
        print("=" * 60)
        print("This is an over-simplified workflow without web search or institutional RAG, with retrieval mode being llamaindex.")
        # Initialize MCP client
        mcp_cleaned = False
        start = time.time()
        await self.mcp_client.connect()
        self.logger.log(
            phase="MCP",
            sender="Workflow",
            receiver="MCP",
            action="mcp_connect",
            duration=round(time.time() - start, 2),
        )

        try:
            # Phase 1: Ingest files
            await self._emit_progress(progress_callback, "ingesting", "Parsing contract and criteria files")
            criteria_md, contract_md = await self._phase_ingest(contract_path, criteria_path)

            # Phase 2: Build index
            await self._emit_progress(progress_callback, "building_index", "Building temporary LlamaIndex contract index")
            await self._phase_build_llamaindex(contract_path)

            # Phase 3: Plan tasks
            await self._emit_progress(progress_callback, "planning", "Extracting review criteria")
            criteria_list = await self._phase_plan(criteria_md)

            # Phase 4: Execute + Reflect
            print(f"\n  Search mode: llamaindex")
            await self._emit_progress(
                progress_callback,
                "reviewing",
                f"Reviewing {len(criteria_list)} criteria with the agent workflow",
            )

            results = await self._phase_execute(criteria_list)

            results_path = self._save_last_results(results)

            # Phase 5: Summarize
            await self._emit_progress(progress_callback, "summarizing", "Creating summary comment")
            summary_sections = await self._phase_summarize(results)

            token_stats = self._collect_token_stats(results)
            total_tokens = token_stats["total"]
            elapsed = round(time.time() - workflow_start, 1)

            # Phase 6: Generate annotated DOCX only
            await self._emit_progress(progress_callback, "generating_docx", "Generating annotated DOCX")
            annotated_docx_path = await self._phase_generate_annotated_docx(
                contract_path=contract_path,
                results=results,
                summary_sections=summary_sections,
                output_dir=output_dir,
                output_path=output_path,
            )

            start = time.time()
            await self.mcp_client.cleanup()
            mcp_cleaned = True
            self.logger.log(
                phase="MCP",
                sender="Workflow",
                receiver="MCP",
                action="mcp_cleanup",
                duration=round(time.time() - start, 2),
            )

            # Save workflow log
            log_path = self.logger.save()
            elapsed = round(time.time() - workflow_start, 1)
            run_summary_path = self._save_run_summary(
                results=results,
                token_stats=token_stats,
                annotated_docx_path=annotated_docx_path,
                elapsed_seconds=elapsed,
                results_path=results_path,
                workflow_log=log_path,
            )
            self._print_completion_summary(
                elapsed,
                token_stats,
                annotated_docx_path,
                log_path,
                run_summary_path,
            )

            await self._emit_progress(progress_callback, "completed", "Review completed")

            return {
                "report_docx": annotated_docx_path,
                "criteria_count": len(results),
                "issue_count": sum(len(result.get("issues", [])) for result in results),
                "total_tokens": total_tokens,
                "retrieval_mode": "llamaindex",
                "workflow_log": log_path,
                "results_log": results_path,
                "run_summary_log": run_summary_path,
            }

        finally:
            if not mcp_cleaned:
                start = time.time()
                await self.mcp_client.cleanup()
                self.logger.log(
                    phase="MCP",
                    sender="Workflow",
                    receiver="MCP",
                    action="mcp_cleanup",
                    duration=round(time.time() - start, 2),
                )

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

    async def _phase_ingest(
            self,
            contract_path: str,
            criteria_path: str
    ) -> tuple[str, str]:
        """Phase 1: Ingest contract + criteria DOCX files."""
        print("\n[Phase 1] Ingesting files...")
        criteria_md = await self._ingest_markdown_file(criteria_path, "criteria")
        contract_md = await self._ingest_markdown_file(contract_path, "contract")

        print(f"  Criteria: {len(criteria_md)} chars")
        print(f"  Contract: {len(contract_md)} chars")
        return criteria_md, contract_md

    async def _ingest_markdown_file(
            self,
            file_path: str,
            input_label: str
    ) -> str:
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

    async def _phase_build_llamaindex(
            self,
            contract_path: str
    ) -> str:
        """Phase 2 (LlamaIndex mode): Build a temporary DOCX-anchor contract vector index."""
        print("\n[Phase 2] Building temporary LlamaIndex contract index...")
        start = time.time()

        result = await self.mcp_client.call_tool(
            "llamaindex_build_index",
            {
                "docx_path": contract_path,
                "api_events_path": self.api_events_path,
            },
        )

        self.logger.log(
            phase="Index Building", sender="Workflow", receiver="MCP:llamaindex_build_index",
            action="llamaindex_build_index",
            input_summary=os.path.basename(contract_path),
            output_summary=result,
            duration=round(time.time() - start, 2)
        )

        parsed = json.loads(result)
        if parsed.get("error"):
            raise classify_model_call_error(
                f"LlamaIndex index build failed: {parsed['error']}",
                default_component="embedding",
            )

        print(f"  Temporary index built in {round(time.time()-start,1)}s: {result[:200]}")
        return result

    async def _phase_plan(
            self,
            criteria_md: str
    ) -> list[dict]:
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
            print(f"    {c['id']}: {c['criterion']}")
        return criteria_list

    async def _phase_execute(
        self,
        criteria_list: list[dict]
    ) -> list[dict]:
        """Phase 4: Orchestrator runs sub-agents with LlamaIndex retrieval + reflection."""
        print(f"\n[Phase 4] Executing {len(criteria_list)} criteria reviews...")
        start = time.time()

        orchestrator = OrchestratorAgent(
            mcp_client=self.mcp_client,
            logger=self.logger,
            settings=self.settings,
            api_events_path=self.api_events_path,
        )
        results = await orchestrator.execute_criteria(criteria_list)
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

    async def _phase_summarize(
            self,
            results: list[dict]
    ) -> dict[str, str]:
        """Phase 5: Summarizer produces overview and priority advice sections."""
        print("\n[Phase 5] Summarizing...")
        start = time.time()

        summarizer = SummarizerAgent(settings=self.settings)
        summary_sections = await summarizer.compile_summary_comment(results)

        self._summarizer_tokens = summarizer.token_usage.get("total_tokens", 0)
        self.logger.log(
            phase="Summarization", sender="Summarizer", receiver="Workflow",
            action="compile_summary_comment",
            input_summary=f"{len(results)} criterion results",
            output_summary=f"{len(json.dumps(summary_sections, ensure_ascii=False))} chars summary",
            tokens=self._summarizer_tokens,
            duration=round(time.time() - start, 2)
        )

        print(f"  Summary sections: {len(summary_sections)}")
        return summary_sections

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

    def _save_last_results(self, results: list[dict]) -> str | None:
        """Persist the raw criterion review results for debugging."""
        if not ENABLE_WORKFLOW_LOGS:
            return None
        if not self.workflow_log_dir:
            return None
        return save_results_json(results, self.workflow_log_dir)

    async def _phase_generate_annotated_docx(
        self,
        contract_path: str,
        results: list[dict],
        summary_sections: dict,
        output_dir: str | None = None,
        output_path: str | None = None,
    ) -> str:
        """Phase 6: Generate only the annotated original-contract DOCX."""
        print("\n[Phase 6] Generating annotated DOCX...")
        start = time.time()
        contract_name = os.path.splitext(os.path.basename(contract_path))[0]
        tool_args = {
            "contract_name": contract_name,
            "contract_path": contract_path,
            "results_json": json.dumps(results, ensure_ascii=False),
            "summary_sections_json": json.dumps(summary_sections, ensure_ascii=False),
        }
        if output_dir is not None:
            tool_args["output_dir"] = output_dir
        if output_path is not None:
            tool_args["output_path"] = output_path

        result = await self.mcp_client.call_tool(
            "generate_docx_report",
            tool_args,
        )

        self.logger.log(
            phase="Report", sender="Workflow", receiver="MCP:generate_docx_report",
            action="generate_docx_report",
            input_summary=f"{len(results)} criterion results",
            output_summary=result,
            duration=round(time.time() - start, 2)
        )

        parsed = json.loads(result)
        if parsed.get("error"):
            raise RuntimeError(f"DOCX report generation failed: {parsed['error']}")
        docx_path = parsed["docx"]
        print(f"  DOCX: {docx_path}")
        return docx_path

    def _save_run_summary(
        self,
        results: list[dict],
        token_stats: dict[str, int],
        annotated_docx_path: str,
        elapsed_seconds: float,
        results_path: str,
        workflow_log: str,
    ) -> str | None:
        """Persist a compact run summary for debugging and audit."""
        if not ENABLE_WORKFLOW_LOGS:
            return None
        phase_durations = self.logger.summarize_phase_durations()
        logged_duration_total = self.logger.total_logged_duration()
        summary = {
            "annotated_docx_path": annotated_docx_path,
            "results_path": results_path,
            "workflow_log": workflow_log,
            "criteria_count": len(results),
            "issue_count": sum(len(result.get("issues", [])) for result in results),
            "error_count": sum(1 for result in results if result.get("status") == "ERROR"),
            "elapsed_seconds": elapsed_seconds,
            "phase_durations": phase_durations,
            "logged_duration_total_seconds": logged_duration_total,
            "duration_gap_seconds": round(elapsed_seconds - logged_duration_total, 2),
            "token_stats": token_stats,
            "criteria_status": [
                {
                    "criterion_id": result.get("criterion_id"),
                    "status": result.get("status"),
                    "issue_count": len(result.get("issues", [])),
                    "tokens": result.get("tokens", 0),
                }
                for result in results
            ],
        }
        if not self.workflow_log_dir:
            return None
        return save_run_summary_json(summary, self.workflow_log_dir)

    def _print_completion_summary(
        self,
        elapsed_seconds: float,
        token_stats: dict[str, int],
        annotated_docx_path: str,
        log_path: str,
        run_summary_path: str,
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
        print(f"Annotated DOCX: {annotated_docx_path}")
        print(f"Run summary: {run_summary_path}")
        print(f"Log: {log_path}")
        print(f"{'=' * 60}")

