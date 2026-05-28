from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.base_agent import Settings
from agents.reflector import ReflectorAgent


DEFAULT_AGENT_OUTPUT_PATH = PROJECT_ROOT / "scripts" / "subagent_result.json"
DEFAULT_CRITERIA_PATH = PROJECT_ROOT / "scripts" / "planner_result.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "scripts" / "reflector_result.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run ReflectorAgent against a saved SubAgent result."
    )
    parser.add_argument(
        "--agent-output",
        default=str(DEFAULT_AGENT_OUTPUT_PATH),
        help="Path to SubAgent result JSON. Defaults to scripts/subagent_result.json.",
    )
    parser.add_argument(
        "--criteria",
        default=str(DEFAULT_CRITERIA_PATH),
        help="Path to Planner result JSON. Defaults to scripts/planner_result.json.",
    )
    parser.add_argument(
        "--criterion-index",
        type=int,
        default=0,
        help="Zero-based criterion index to use from the planner result.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Path for writing ReflectorAgent result JSON.",
    )
    return parser


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"JSON file does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_criterion(criteria_path: Path, criterion_index: int) -> dict:
    data = read_json(criteria_path)
    criteria = data.get("criteria") if isinstance(data, dict) else data
    if not isinstance(criteria, list):
        raise ValueError("Criteria JSON must be a list or an object with a 'criteria' list.")
    try:
        criterion = criteria[criterion_index]
    except IndexError as exc:
        raise IndexError(
            f"criterion-index {criterion_index} is out of range; criteria count is {len(criteria)}."
        ) from exc
    if not isinstance(criterion, dict):
        raise ValueError("Selected criterion must be a JSON object.")
    return criterion


def build_evaluation_criteria(criterion: dict) -> str:
    criterion_text = criterion["criterion"]
    check_points = criterion.get("check_points", [])
    check_points_text = "\n".join(f"- {cp}" for cp in check_points)
    return f"审查标准：{criterion_text}\n检查要点：\n{check_points_text}"


async def run_reflector(
    agent_output_path: Path,
    criteria_path: Path,
    criterion_index: int,
    output_path: Path,
) -> dict:
    agent_output = read_json(agent_output_path)
    criterion = load_criterion(criteria_path, criterion_index)
    evaluation_criteria = build_evaluation_criteria(criterion)

    reflector = ReflectorAgent(settings=Settings())
    result = await reflector.review(
        agent_output=json.dumps(agent_output, ensure_ascii=False, indent=2),
        evaluation_criteria=evaluation_criteria,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


async def main() -> dict:
    args = build_parser().parse_args()
    return await run_reflector(
        agent_output_path=Path(args.agent_output).expanduser().resolve(),
        criteria_path=Path(args.criteria).expanduser().resolve(),
        criterion_index=args.criterion_index,
        output_path=Path(args.output).expanduser().resolve(),
    )


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main()), ensure_ascii=False, indent=2))
