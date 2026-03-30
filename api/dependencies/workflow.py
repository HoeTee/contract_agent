from functools import lru_cache

from config import MCP_SERVER_URL
from main_workflow.main_workflow import ContractReviewWorkflow


@lru_cache()
def get_workflow():
    """Singleton pattern to get workflow instance."""
    return ContractReviewWorkflow(server_script_path=MCP_SERVER_URL)
