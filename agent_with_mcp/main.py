"""
Entry point for the contract review workflow.
"""
import asyncio
import os

# Project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# File paths — change these to your actual files
CONTRACT_PATH = os.path.join(
    PROJECT_ROOT, 
    "docs/contracts", "反馈0730-【已审查】（190号）互联网类系统CDN加速服务（三年）采购合同HT-ZRUB-2025-07-01-08-C002.docx"
)
CRITERIA_PATH = os.path.join(
    PROJECT_ROOT, 
    "docs/contract_review_criteria", 
    "审核要点（初稿）.docx"
)
MCP_SERVER_PATH = os.path.join(
    PROJECT_ROOT, 
    "mcp_service", 
    "mcp_server", 
    "mcp_server.py"
)


async def main():
    from main_workflow.main_workflow import ContractReviewWorkflow

    workflow = ContractReviewWorkflow(server_script_path=MCP_SERVER_PATH)
    result = await workflow.run(
        contract_path=CONTRACT_PATH,
        criteria_path=CRITERIA_PATH,
    )
    print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())
