import logging
import sys
import os

# Configure logging
logger = logging.getLogger("MCPClient")
logger.setLevel(logging.DEBUG)

# File handler with DEBUG level - store in mcp_client directory
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logger")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "mcp_client.log")
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)

# Console handler with INFO level
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)