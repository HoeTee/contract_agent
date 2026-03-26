"""
SummarizerAgent — compiles all sub-agent review results into a final report.
No MCP access. Pure text compilation.
"""
import re
import asyncio
from string import Template

from agents.base_agent import Agent
from agents.prompts.cn_prompts import SUMMARIZER_SYSTEM_PROMPT, FORMATTER_SYSTEM_PROMPT


class SummarizerAgent(Agent):
    """Compiles sub-agent outputs into a complete review report."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt=SUMMARIZER_SYSTEM_PROMPT,
            name="Summarizer",
            **kwargs
        )

    def _filter_compliant_or_error_blocks(self, text: str) -> str:
        """Filter out check points with '无' risk level or '[ALL_COMPLIANT]'."""
        if not text:
            return ""
        if "[ALL_COMPLIANT]" in text or "ERROR" in text:
            return ""
            
        parts = re.split(r'(### 检查要点[：:])', text)
        if len(parts) == 1:
            if re.search(r'风险等级[*\s:：]*无', text):
                return ""
            return text.strip()
            
        filtered_text = parts[0]
        for i in range(1, len(parts), 2):
            header = parts[i]
            content = parts[i+1] if i+1 < len(parts) else ""
            if not re.search(r'风险等级[*\s:：]*无', content):
                filtered_text += header + content
                
        return filtered_text.strip()

    async def format_single_result(self, major_idx: int, minor_idx: int, criterion: str, raw_output: str) -> dict:
        """
        Format the review output for a single check point.
        """
        formatter_prompt = Template(FORMATTER_SYSTEM_PROMPT).substitute(
            major_idx=major_idx, 
            minor_idx=minor_idx,
            criterion=criterion
        )
        formatter = Agent(system_prompt=formatter_prompt, name=f"Formatter-{major_idx}.{minor_idx}")
        response = await formatter.chat(f"原始审查输出如下（请重构为标准客观的分析格式）：\n{raw_output}")
        
        return {
            "formatted_text": response,
            "tokens": formatter.token_usage.get("total_tokens", 0),
            "prompt_tokens": formatter.token_usage.get("prompt_tokens", 0),
            "completion_tokens": formatter.token_usage.get("completion_tokens", 0)
        }

    async def compile_report(self, results: list[dict]) -> str:
        """
        Compile all criterion review results into a final report.
        Args:
            results: list of {"criterion_id", "criterion", "review_output", "status", "section"} dicts
        Returns: complete report markdown string
        """
        # Group results by section
        from collections import defaultdict
        section_groups = defaultdict(list)
        unique_sections = []
        
        for r in results:
            out = r.get('review_output', '')
            filtered_out = self._filter_compliant_or_error_blocks(out)
            if not filtered_out:
                continue
            
            section_name = r.get('section', '其他')
            if section_name not in unique_sections:
                unique_sections.append(section_name)
            section_groups[section_name].append({
                "criterion": r['criterion'],
                "output": filtered_out
            })

        sections = []
        major_idx = 1
        format_tasks = []
        task_metadata = []
        
        # Build the formatting tasks
        for section_name in unique_sections:
            items = section_groups[section_name]
            minor_idx = 1
            for item in items:
                format_tasks.append(
                    self.format_single_result(major_idx, minor_idx, item['criterion'], item['output'])
                )
                task_metadata.append((section_name, major_idx))
                minor_idx += 1
            major_idx += 1

        print(f"    [Summarizer] Launching {len(format_tasks)} formatting sub-agents concurrently...")
        formatted_results = await asyncio.gather(*format_tasks)
        print(f"    [Summarizer] Formatting completed.")
        
        # Group back organized texts
        grouped_formatted = defaultdict(list)
        for meta, res in zip(task_metadata, formatted_results):
            section_name = meta[0]
            grouped_formatted[section_name].append(res["formatted_text"])
            self.token_usage["total_tokens"] = self.token_usage.get("total_tokens", 0) + res.get("tokens", 0)
            self.token_usage["prompt_tokens"] = self.token_usage.get("prompt_tokens", 0) + res.get("prompt_tokens", 0)
            self.token_usage["completion_tokens"] = self.token_usage.get("completion_tokens", 0) + res.get("completion_tokens", 0)
            
        for section_name in unique_sections:
            items = grouped_formatted[section_name]
            sections.append(f"### {section_name}")
            for text in items:
                sections.append(text)

        all_results = "\n\n".join(sections)
        prompt = f"""
        一共有{len(results)}项审查标准参与了审查。请根据以下各项审查结果，生成审查报告。
        注意在【一、审查概要】中准确写明审查标准数量为{len(results)}项，不要自己数错，必须是这个数字。
        在【三、审查详情】下严格输出占位符 [INSERT_DETAILS_HERE] ，不要自行编写任何详情内容：\n\n{all_results}
        """
        
        summary_report = await self.chat(prompt)
        
        # Replace the placeholder with the actual, perfectly-formatted sub-agent details
        if "[INSERT_DETAILS_HERE]" in summary_report:
            final_report = summary_report.replace("[INSERT_DETAILS_HERE]", all_results)
        else:
            # Fallback in case the LLM disobeys the prompt
            final_report = f"{summary_report}\n\n## 四、审查详情 (Fallback Appended)\n\n{all_results}"
            
        return final_report
