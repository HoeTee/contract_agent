from __future__ import annotations

import asyncio

from config import MAX_API_CONCURRENT_REVIEWS


review_semaphore = (
    asyncio.Semaphore(MAX_API_CONCURRENT_REVIEWS)
    if MAX_API_CONCURRENT_REVIEWS > 0
    else None
)
