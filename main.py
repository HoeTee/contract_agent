"""
Entry point for the contract review workflow.
"""
import asyncio
import os
from main_workflow.main_workflow import ContractReviewWorkflow

# Project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

doc_1 = "【已审查】（214号）浙江农商与移动浙江公司集团固话业务协议-修订4(1).docx"
doc_2 = "【已审查】（528号）2026年至2028年贵宾医疗服务合作协议-邵逸夫医院.docx"
doc_3 = "【已审核】（262号）产品单次销售合同-卡券、实物、定点配送（东福、东乐通用型模版） (4).docx"

# File Format Exam
def contract_path(filename):

    ALLOWED_FORMATS = {".pdf", ".docx"} # a set
    def extract_ext(filename):
        return os.path.splitext(filename)[1].lower()

    if not extract_ext() in ALLOWED_FORMATS:
        raise ValueError(f".{os.path.splitext(filename)[1].lower()} is not in an allowed format.")
    
    return os.path.join(
        PROJECT_ROOT, 
        "docs/contracts", 
        filename
    )

# File paths — change these to your actual files
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


async def main(filename: str=doc_1):

    CONTRACT_PATH = contract_path(filename) 

    workflow = ContractReviewWorkflow(server_script_path=MCP_SERVER_PATH)
    result = await workflow.run(
        contract_path=CONTRACT_PATH,
        criteria_path=CRITERIA_PATH,
    )
    print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())
