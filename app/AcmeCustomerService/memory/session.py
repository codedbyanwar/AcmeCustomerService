"""AgentCore Memory session manager (ported from the reference project).

Keyed on the resolved Acme customer id (memory_key, e.g. 'cust-a-sub') rather
than on the caller JWT, because the business identity is resolved in-chat.

Gracefully returns None when MEMORY_SHAREDMEMORY_ID is unset so the agent runs
locally ($0) without a provisioned Memory resource.
"""

import os
from typing import Optional

MEMORY_ID = os.getenv("MEMORY_SHAREDMEMORY_ID")
REGION = os.getenv("AWS_REGION")


def get_memory_session_manager(session_id: str, actor_id: str):
    """Return an AgentCoreMemorySessionManager, or None if Memory is not configured."""
    if not MEMORY_ID:
        return None

    # Imported lazily so the module loads even without the memory extras locally.
    from bedrock_agentcore.memory.integrations.strands.config import (
        AgentCoreMemoryConfig,
        RetrievalConfig,
    )
    from bedrock_agentcore.memory.integrations.strands.session_manager import (
        AgentCoreMemorySessionManager,
    )

    retrieval_config = {
        f"/users/{actor_id}/facts": RetrievalConfig(top_k=3, relevance_score=0.3),
        f"/summaries/{actor_id}/{session_id}": RetrievalConfig(top_k=3, relevance_score=0.3),
    }

    return AgentCoreMemorySessionManager(
        AgentCoreMemoryConfig(
            memory_id=MEMORY_ID,
            session_id=session_id,
            actor_id=actor_id,
            retrieval_config=retrieval_config,
        ),
        REGION,
    )
