"""
SummarizerAgent — compiles all sub-agent review results into a final report.
No MCP access. Pure text compilation.
"""
import re
import asyncio

from agents.base_agent import Agent
from agents.prompts.cn_prompts import SUMMARIZER_SYSTEM_PROMPT


class SummarizerAgent(Agent):
    """Compiles sub-agent outputs into a complete review report."""

    def __init__(self, **kwargs):
        super().__init__(
            system_prompt=SUMMARIZER_SYSTEM_PROMPT,
            name="Summarizer",
            **kwargs
        )

    def _filter_compliant_blocks(self, text: str) -> str:
        """Filter out check points with '无' risk level or '[ALL_COMPLIANT]'."""
        if not text:
            return ""
        if "[ALL_COMPLIANT]" in text:
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
        formatter_prompt = f"""
        你是一个专门负责格式化合同审查意见的AI报告整理专家。
        你的任务是接收原始的审查输出内容，并将其严格按照给定的Markdown格式标准进行重构和整合润色。

        当前处理的检查要点编号：{major_idx}.{minor_idx}
        当前检查要点要求的内容：{criterion}

        【格式要求】
        1. 必须严格按照以下Markdown结构输出，绝对不要输出任何结构之外的寒暄语或解释性文字。
        2. 请直接把原本带有序号的检查要点要求内容去掉最前面的数字序号（如删掉“1.”、“2.”等前缀），将核心检查内容整合到标题中。
        3. 请重新梳理论述原本的【风险等级】、【审查结论】、【原文引用】、【问题分析】、【法律依据】、【修改建议】，去除掉第一人称或口语化的表述（例如“根据审查标准和合同内容分析，我发现...”），使之成为直接、客观专业的风险提示与修改建议。
        4. 确保排版整洁，所有对应的字段如果不适用或者没有，可以写“无”或者略过。

        【输出模板结构】（请严格按照此模板填充内容）：

        #### 检查要点 {major_idx}.{minor_idx}：[将上面的检查要点剥离数字序号后填入这里]

        - **风险等级**：[提取原始输出中的风险等级（如高/中/低）]
        - **审查结论**：[精确、客观、直接的结论]
        - **原文引用**：
        > [提取相关的原文部分]
        - **所在位置**：[条款的具体位置]
        - **问题分析**：[专业的风险剖析]
        - **法律依据**：[适用的法律法则或行业规定]
        - **修改建议**：
        > [具体的修订意见或示范性条款]

        注意：绝对不要再输出类似于“### 检查要点：xxx”这种重复的标题，必须严格按照“#### 检查要点 X.Y：xxx”这种格式进行输出。
        """
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
            filtered_out = self._filter_compliant_blocks(out)
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
            self.token_usage["total_tokens"] = self.token_usage.get("total_tokens", 0) + res["tokens"]
            self.token_usage["prompt_tokens"] = self.token_usage.get("prompt_tokens", 0) + res.get("prompt_tokens", 0)
            self.token_usage["completion_tokens"] = self.token_usage.get("completion_tokens", 0) + res.get("completion_tokens", 0)
            
        for section_name in unique_sections:
            items = grouped_formatted[section_name]
            sections.append(f"### {section_name}")
            for text in items:
                sections.append(text)

        all_results = "\n\n".join(sections)
        prompt = f"一共有{len(results)}项审查标准参与了审查。请根据以下各项审查结果，生成审查报告。注意在【一、审查概要】中准确写明审查标准数量为{len(results)}项，不要自己数错，必须是这个数字。在【三、审查详情】下严格输出占位符 [INSERT_DETAILS_HERE] ，不要自行编写任何详情内容：\n\n{all_results}"
        
        summary_report = await self.chat(prompt)
        
        # Replace the placeholder with the actual, perfectly-formatted sub-agent details
        if "[INSERT_DETAILS_HERE]" in summary_report:
            final_report = summary_report.replace("[INSERT_DETAILS_HERE]", all_results)
        else:
            # Fallback in case the LLM disobeys the prompt
            final_report = f"{summary_report}\n\n## 四、审查详情 (Fallback Appended)\n\n{all_results}"
            
        return final_report
