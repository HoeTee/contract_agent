"""
EvidenceCollectorAgent — collects relevant text fragments from each contract
section for a given review criterion.

When PAGEINDEX_SEARCH=False, this agent replaces the pageindex_search MCP tool
by iterating through every section in the tree_json, making one LLM call per
section to extract only the text fragments relevant to the criterion.
"""
import asyncio
import json

from agents.base_agent import Agent, Settings
from agents.prompts.cn_prompts import EVIDENCE_COLLECTOR_PROMPT


class EvidenceCollectorAgent:
    """Collects fine-grained evidence from contract sections for a criterion."""

    def __init__(self, settings: Settings = None):
        self.settings = settings or Settings()
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # ==================== Tree Helpers ====================

    @staticmethod
    def _flatten_tree(tree_json: str) -> list[dict]:
        """
        Flatten a PageIndex tree into a list of nodes with text and path.

        Returns:
            List of {"path": "第三条 > 3.2", "title": "3.2 服务费用", "text": "..."}
        """
        tree = json.loads(tree_json) if isinstance(tree_json, str) else tree_json
        nodes = []

        def _walk(node, ancestors: list[str]):
            """Recursively walk tree, collecting nodes that have text."""
            if isinstance(node, dict):
                title = node.get("title", "")
                current_path = ancestors + ([title] if title else [])

                # If this node has text, record it
                if node.get("text", "").strip():
                    nodes.append({
                        "path": " > ".join(current_path),
                        "title": title,
                        "text": node["text"],
                    })

                # Recurse into children (could be under "structure" or "nodes")
                for key in ("structure", "nodes", "children"):
                    child = node.get(key)
                    if child:
                        _walk(child, current_path)

            elif isinstance(node, list):
                for item in node:
                    _walk(item, ancestors)

        _walk(tree, [])
        return nodes

    # ==================== Per-Section LLM Call ====================

    async def _extract_from_section(
        self, criterion_text: str, check_points_text: str, section: dict
    ) -> dict | None:
        """
        Make one LLM call to extract relevant text from a single section.

        Returns:
            {"source": "path", "relevant_text": "..."} or None if not relevant.
        """
        agent = Agent(
            system_prompt=EVIDENCE_COLLECTOR_PROMPT,
            name=f"EvidenceCollector",
            settings=self.settings,
        )

        prompt = (
            f"审查标准：{criterion_text}\n"
            f"检查要点：\n{check_points_text}\n\n"
            f"以下是合同章节【{section['path']}】的文本内容：\n\n"
            f"{section['text']}"
        )

        response = await agent.chat(prompt)

        # Accumulate token usage
        for k in self.token_usage:
            self.token_usage[k] += agent.token_usage.get(k, 0)

        # Parse JSON response
        text = response.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    result = json.loads(text[start:end])
                except json.JSONDecodeError:
                    return None
            else:
                return None

        relevant = result.get("relevant_text", "").strip()
        if not relevant:
            return None

        return {
            "source": section["path"],
            "relevant_text": relevant,
        }

    # ==================== Main Collection ====================

    async def collect_evidence(
        self, criterion: dict, tree_json: str
    ) -> list[dict]:
        """
        Collect evidence for one criterion by iterating all tree sections.

        Args:
            criterion: {"id", "criterion", "check_points", ...}
            tree_json: The full PageIndex tree JSON string.

        Returns:
            List of {"source": "path", "relevant_text": "extracted fragment"}
        """
        cid = criterion["id"]
        criterion_text = criterion["criterion"]
        check_points = criterion.get("check_points", [])
        check_points_text = "\n".join(f"- {cp}" for cp in check_points)

        # Flatten tree to get all sections with text
        sections = self._flatten_tree(tree_json)
        print(f"[EvidenceCollector] {cid}: Scanning {len(sections)} sections...")

        # Run all section extractions concurrently
        tasks = [
            self._extract_from_section(criterion_text, check_points_text, section)
            for section in sections
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out None and exceptions
        evidence = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                print(f"[EvidenceCollector] {cid}: Error on section '{sections[i]['path']}': {r}")
            elif r is not None:
                evidence.append(r)

        print(f"[EvidenceCollector] {cid}: Found {len(evidence)} relevant sections")
        return evidence

    @staticmethod
    def format_evidence(evidence: list[dict]) -> str:
        """
        Format collected evidence into a readable string for the SubAgent.

        Output format:
        ### 出处：第三条 服务 > 3.2 服务费用
        > relevant text fragment...

        ### 出处：第七条 知识产权 > 7.1
        > relevant text fragment...
        """
        if not evidence:
            return "未找到相关内容"

        parts = []
        for item in evidence:
            source = item["source"]
            text = item["relevant_text"]
            # Wrap each line in blockquote for readability
            quoted = "\n".join(f"> {line}" for line in text.split("\n"))
            parts.append(f"### 出处：{source}\n{quoted}")

        return "\n\n".join(parts)
