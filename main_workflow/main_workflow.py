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
import asyncio
import json
import os
import time

from config import PROJECT_ROOT, MCP_SERVER_PATH, REPORTS_DIR, LOGS_DIR, PAGEINDEX_SEARCH
from main_workflow.workflow_logger import WorkflowLogger
from agents.base_agent import Settings
from agents.planner import PlannerAgent
from agents.orchestrator import OrchestratorAgent
from agents.summarizer import SummarizerAgent
from mcp_service.mcp_client.mcp_minimal import MinimalMCPClient


class ContractReviewWorkflow:
    """Full contract review pipeline."""

    def __init__(self, server_script_path: str = MCP_SERVER_PATH):
        self.mcp_client = MinimalMCPClient(server_script_path)
        self.logger = WorkflowLogger()
        self.settings = Settings()

    async def run(self, contract_path: str, criteria_path: str) -> str:
        """
        Execute the full review workflow.
        Returns: path to generated report.
        """
        workflow_start = time.time()
        print("=" * 60)
        print("Contract Review Workflow")
        print("=" * 60)

        # Initialize MCP client
        await self.mcp_client.connect()

        try:
            # Phase 1: Ingest files
            criteria_md, contract_md = await self._phase_ingest(contract_path, criteria_path)

            # Phase 2: Build PageIndex tree
            tree_json = await self._phase_build_tree(contract_md)

            # Phase 3: Plan tasks
            criteria_list = await self._phase_plan(criteria_md)

            # Phase 4: Execute + Reflect
            mode_label = "PageIndex Search" if PAGEINDEX_SEARCH else "Evidence Collector"
            print(f"\n  Search mode: {mode_label}")
            results = await self._phase_execute(criteria_list, tree_json)

            # Phase 5: Summarize
            report_text = await self._phase_summarize(results)

            # Append criteria coverage checklist
            checklist = self._build_checklist(criteria_list, results)
            report_text += checklist

            # Aggregate token usage from all phases
            planner_tokens = getattr(self, '_planner_tokens', 0)
            execute_tokens = sum(r.get("tokens", 0) for r in results)
            summarizer_tokens = getattr(self, '_summarizer_tokens', 0)
            total_tokens = planner_tokens + execute_tokens + summarizer_tokens

            # Append token stats to report
            token_stats = (
                f"\n\n---\n\n"
                f"## 附：Token 消耗统计\n\n"
                f"| 阶段 | Token 消耗 |\n"
                f"|------|----------|\n"
                f"| 规划（Planner） | {planner_tokens:,} |\n"
                f"| 审查（Sub-Agents + Reflectors） | {execute_tokens:,} |\n"
                f"| 汇总（Summarizer） | {summarizer_tokens:,} |\n"
                f"| **合计** | **{total_tokens:,}** |\n"
            )
            report_text += token_stats

            # Phase 6: Generate reports (MD + DOCX + PDF)
            elapsed = round(time.time() - workflow_start, 1)
            report_path = await self._phase_generate_report(
                report_text, contract_path,
                elapsed_seconds=elapsed, results=results,
            )

            # Save workflow log
            log_path = self.logger.save()
            elapsed = round(time.time() - workflow_start, 1)
            mins, secs = divmod(int(elapsed), 60)
            print(f"\n{'=' * 60}")
            print(f"Workflow complete! Total time: {mins}m {secs}s")
            print(f"Total tokens: {total_tokens:,} (Planner: {planner_tokens:,} | Execute: {execute_tokens:,} | Summarizer: {summarizer_tokens:,})")
            print(f"Report: {report_path}")
            print(f"Log: {log_path}")
            print(f"{'=' * 60}")

            return report_path

        finally:
            await self.mcp_client.cleanup()

    # ==================== Phases ====================

    async def _phase_ingest(self, contract_path: str, criteria_path: str) -> tuple[str, str]:
        """Phase 1: Ingest contract + criteria DOCX files."""
        print("\n[Phase 1] Ingesting files...")
        t1 = time.time()

        criteria_result = await self.mcp_client.call_tool(
            "ingest_docx", {"file_path": criteria_path}
        )
        self.logger.log(
            phase="Ingestion", sender="Workflow", receiver="MCP:ingest_docx",
            action="ingest_docx(criteria)",
            input_summary=os.path.basename(criteria_path),
            output_summary=f"{len(criteria_result)} chars",
            duration=round(time.time() - t1, 2)
        )

        t2 = time.time()
        contract_result = await self.mcp_client.call_tool(
            "ingest_docx", {"file_path": contract_path}
        )
        self.logger.log(
            phase="Ingestion", sender="Workflow", receiver="MCP:ingest_docx",
            action="ingest_docx(contract)",
            input_summary=os.path.basename(contract_path),
            output_summary=f"{len(contract_result)} chars",
            duration=round(time.time() - t2, 2)
        )

        # Extract markdown content (skip the "File ingested..." header)
        criteria_md = criteria_result.split("\n\n", 1)[-1] if "\n\n" in criteria_result else criteria_result
        contract_md = contract_result.split("\n\n", 1)[-1] if "\n\n" in contract_result else contract_result

        print(f"  Criteria: {len(criteria_md)} chars")
        print(f"  Contract: {len(contract_md)} chars")
        return criteria_md, contract_md

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

    async def _phase_execute(self, criteria_list: list[dict], tree_json: str) -> list[dict]:
        """Phase 4: Orchestrator runs sub-agents with PageIndex retrieval + reflection."""
        print(f"\n[Phase 4] Executing {len(criteria_list)} criteria reviews...")
        start = time.time()

        orchestrator = OrchestratorAgent(
            mcp_client=self.mcp_client,
            logger=self.logger,
            settings=self.settings,
        )
        results = await orchestrator.execute_criteria(criteria_list, tree_json)

        self.logger.log(
            phase="Execution", sender="Orchestrator", receiver="Workflow",
            action="execute_criteria_complete",
            input_summary=f"{len(criteria_list)} criteria",
            output_summary=f"{len(results)} results",
            duration=round(time.time() - start, 2)
        )

        print(f"  Completed: {len(results)} reviews")
        return results

    async def _phase_summarize(self, results: list[dict]) -> str:
        """Phase 5: Summarizer compiles all results into report text."""
        print("\n[Phase 5] Summarizing...")
        start = time.time()

        summarizer = SummarizerAgent(settings=self.settings)
        report_text = await summarizer.compile_report(results)

        self._summarizer_tokens = summarizer.token_usage.get("total_tokens", 0)
        self.logger.log(
            phase="Summarization", sender="Summarizer", receiver="Workflow",
            action="compile_report",
            input_summary=f"{len(results)} criterion results",
            output_summary=f"{len(report_text)} chars report",
            tokens=self._summarizer_tokens,
            duration=round(time.time() - start, 2)
        )

        print(f"  Report: {len(report_text)} chars")
        return report_text

    def _build_checklist(self, criteria_list: list[dict], results: list[dict]) -> str:
        """Build a criteria coverage checklist including individual check_points."""
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

    async def _phase_generate_report(
        self, report_text: str, contract_path: str,
        elapsed_seconds: float = None, results: list = None,
    ) -> str:
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
        return result
