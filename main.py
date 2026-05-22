"""
Entry point for the contract review workflow.
"""
import asyncio
import os
from dotenv import load_dotenv
from main_workflow.main_workflow import ContractReviewWorkflow

# Project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

doc_1 = "【已审查】（214号）浙江农商与移动浙江公司集团固话业务协议-修订4(1).docx"
doc_2 = "【已审查】（528号）2026年至2028年贵宾医疗服务合作协议-邵逸夫医院.docx"
doc_3 = "【已审核】（262号）产品单次销售合同-卡券、实物、定点配送（东福、东乐通用型模版） (4).docx"
doc_4 = "【已审查】（312号）关于联合开展普惠金融服务共同富裕课题研究及推广宣传活动服务采购合同（ZRUB-2025-08-28-19-E001）.docx"
doc_5 = "【已审查】（355号）省行IaaS云计算平台扩容及驻场运维服务采购（二期）合同-初稿.docx"
doc_6 = "【已审查】（397号）2025年世界互联网大会“互联网之光”博览会网络安全主题展服务项目申购协议书.docx"
doc_7 = "【已审查】（433号）ZRUBXC软件开发类采购合同-人行支付系统重构项目-20251110.docx"
doc_8 = "【已审查】（408号）浙江农商联合银行2025年体检服务协议.docx"
doc_9 = "【已审查】（456号）农商财富大厦办公场地租赁合同11.17.docx"
doc_10 = "【已审查】（370号）浙江农商联合银行科技大楼绿植墙优化及养护合同V1.0.docx"

# File Format Exam
def contract_path(filename):

    ALLOWED_FORMATS = {".pdf", ".docx"} # a set
    def extract_ext(filename):
        return os.path.splitext(filename)[1].lower()

    if extract_ext(filename) not in ALLOWED_FORMATS:
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
    "审核要点（初稿）(2).docx"
)
MCP_SERVER_PATH = os.path.join(
    PROJECT_ROOT, 
    "mcp_service", 
    "mcp_server", 
    "mcp_server.py"
)
CLI_OUTPUT_DIR = os.getenv(
    "CLI_OUTPUT_DIR",
    os.path.join(PROJECT_ROOT, "docs", "reports_docx"),
)


async def main(filename: str=doc_10):

    CONTRACT_PATH = contract_path(filename) 

    workflow = ContractReviewWorkflow(server_script_path=MCP_SERVER_PATH)
    result = await workflow.run(
        contract_path=CONTRACT_PATH,
        criteria_path=CRITERIA_PATH,
        output_dir=CLI_OUTPUT_DIR,
    )
    # print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())
