from functools import lru_cache
from main_workflow.main_workflow import ContractReviewWorkflow
import os


@lru_cache()
def get_workflow():
    """Singleton pattern to get workflow instance"""
    server_script_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "mcp_service",
        "mcp_server",
        "mcp_server.py"
    )
    return ContractReviewWorkflow(server_script_path=server_script_path)