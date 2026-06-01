"""
Local CLI entry point for the contract review workflow.
"""
import argparse
import asyncio
from pathlib import Path
import shutil

from dotenv import load_dotenv

from config import DATA_DIR, DEFAULT_CLI_USERNAME, ENV_PATH, MCP_SERVER_PATH
from loggers.agent_logger import reset_conversation_log_dir, set_conversation_log_dir
from loggers.resolve_review_task_paths import resolve_review_task_paths
from main_workflow.main_workflow import ContractReviewWorkflow
from web.routes import validate_uploaded_docx


load_dotenv(ENV_PATH)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local contract review.")
    parser.add_argument(
        "--username",
        default=DEFAULT_CLI_USERNAME,
        help="User partition under data/. Defaults to DEFAULT_CLI_USERNAME.",
    )
    parser.add_argument(
        "--contract",
        required=True,
        help="Contract filename under data/<username>/contracts or an absolute path.",
    )
    return parser


def resolve_contract_path(username: str, contract: str) -> Path:
    path = Path(contract)
    if path.is_absolute():
        return path
    return Path(DATA_DIR) / username / "contracts" / contract


async def run_cli(username: str, contract: str) -> dict:
    contract_path = resolve_contract_path(username, contract)
    if not contract_path.exists():
        raise FileNotFoundError(f"未找到合同文件：{contract_path}")

    paths = resolve_review_task_paths(
        username=username,
        original_filename=contract_path.name,
        data_dir=Path(DATA_DIR),
    )
    paths.ensure_task_dirs()

    if not paths.criteria_path.exists():
        raise FileNotFoundError(f"未找到审查要点文件：{paths.criteria_path}")

    if contract_path.resolve() != paths.stored_contract_path.resolve():
        shutil.copy2(contract_path, paths.stored_contract_path)

    validate_uploaded_docx(paths.stored_contract_path)

    token = set_conversation_log_dir(paths.conversation_log_dir)
    try:
        workflow = ContractReviewWorkflow(
            server_script_path=MCP_SERVER_PATH,
            workflow_log_dir=str(paths.workflow_log_dir),
            conversation_log_dir=str(paths.conversation_log_dir),
            mcp_log_file=str(paths.mcp_log_dir / "mcp_client.log"),
        )
        result = await workflow.run(
            contract_path=str(paths.stored_contract_path),
            criteria_path=str(paths.criteria_path),
            output_path=str(paths.final_report_path),
        )
    finally:
        reset_conversation_log_dir(token)

    result["final_report_docx"] = str(paths.final_report_path)
    print(f"Final report: {paths.final_report_path}")
    return result


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run_cli(args.username, args.contract))


if __name__ == "__main__":
    main()
