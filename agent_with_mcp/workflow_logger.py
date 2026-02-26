"""
Workflow Logger — records every info flow step and generates
a Markdown report with Mermaid sequence diagram.
"""
import os
import time
from datetime import datetime
from config import LOGS_DIR


class WorkflowLogger:
    """Records workflow steps and generates MD + Mermaid log."""

    def __init__(self):
        self.steps = []
        self.start_time = time.time()

    def log(self, phase: str, sender: str, receiver: str,
            action: str, input_summary: str = "", output_summary: str = "",
            tokens: int = 0, duration: float = 0.0):
        """Record one info-flow step."""
        from config import MAX_CONTEXT_TOKENS
        
        ctx_pct = ""
        if tokens > 0 and MAX_CONTEXT_TOKENS > 0:
            pct = int((tokens / MAX_CONTEXT_TOKENS) * 100)
            ctx_pct = f" ({pct}%)"

        self.steps.append({
            "step": len(self.steps) + 1,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "phase": phase,
            "sender": sender,
            "receiver": receiver,
            "action": action,
            "input": input_summary,
            "output": output_summary,
            "tokens": f"{tokens}{ctx_pct}" if tokens else "—",
            "raw_tokens": tokens,
            "duration": round(duration, 2),
        })

    def _build_mermaid(self) -> str:
        """Generate Mermaid sequence diagram from logged steps."""
        def sanitize_id(n: str) -> str:
            return n.replace(" ", "_").replace(":", "_").replace("-", "_")

        # Collect unique participants in order of first appearance
        seen = {}
        for s in self.steps:
            for name in [s["sender"], s["receiver"]]:
                if name not in seen:
                    seen[name] = len(seen)

        lines = ["```mermaid", "sequenceDiagram"]
        for name in seen:
            alias = sanitize_id(name)
            lines.append(f"    participant {alias} as \"{name}\"")

        for s in self.steps:
            src = sanitize_id(s["sender"])
            dst = sanitize_id(s["receiver"])
            label = s["action"]
            if s["duration"]:
                label += f" ({s['duration']}s)"
            lines.append(f"    {src}->>{dst}: {label}")

        lines.append("```")
        return "\n".join(lines)

    def _build_steps_md(self) -> str:
        """Generate per-step detail blocks."""
        blocks = []
        for s in self.steps:
            # Format I/O in grey blocks
            input_text = f"\n```text\n{s['input']}\n```\n" if s['input'] else "—"
            output_text = f"\n```text\n{s['output']}\n```\n" if s['output'] else "—"
            
            block = f"""### Step {s['step']} — {s['action']}

- **Time**: {s['timestamp']}
- **Phase**: {s['phase']}
- **Sender**: {s['sender']}
- **Receiver**: {s['receiver']}
- **Action**: {s['action']}
- **Input**: {input_text}
- **Output**: {output_text}
- **Tokens**: {s['tokens']}
- **Duration**: {s['duration']}s
"""
            blocks.append(block)
        return "\n".join(blocks)

    def save(self) -> str:
        """Write the complete log to a Markdown file."""
        os.makedirs(LOGS_DIR, exist_ok=True)

        total_time = round(time.time() - self.start_time, 2)
        total_tokens = sum(s.get("raw_tokens", 0) for s in self.steps)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(LOGS_DIR, f"workflow_{ts}.md")

        content = f"""# Workflow Log — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Total Steps**: {len(self.steps)} | **Total Time**: {total_time}s | **Total Tokens**: {total_tokens}

---

## Flow Diagram

{self._build_mermaid()}

---

## Detailed Steps

{self._build_steps_md()}
"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"[Logger] Workflow log saved: {filepath}")
        return filepath
