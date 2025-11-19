"""API v2 router for MemMachine project and memory management endpoints."""

from typing import Annotated
from urllib import parse

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import ValidationError

from memmachine.common.configuration.episodic_config import (
    EpisodicMemoryConf,
    LongTermMemoryConf,
    ShortTermMemoryConf,
)
from memmachine.common.session_manager.session_data_manager import SessionDataManager
from memmachine.episode_store.episode_model import ContentType, Episode, EpisodeType
from uuid import uuid4
from memmachine.episodic_memory.episodic_memory import EpisodicMemory
from memmachine.episodic_memory.episodic_memory_manager import EpisodicMemoryManager
from memmachine.server.api_v2.filter_parser import parse_filter
from memmachine.server.api_v2.spec import (
    AddMemoriesSpec,
    CreateProjectSpec,
    DeleteEpisodicMemorySpec,
    DeleteMemoriesSpec,
    DeleteProjectSpec,
    DeleteSemanticMemorySpec,
    ListMemoriesSpec,
    SearchMemoriesSpec,
    SearchResult,
    SessionInfo,
)

router = APIRouter()


async def get_session_info(request: Request) -> SessionInfo:
    """Get session info instance."""
    try:
        body = await request.json()
        return SessionInfo.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e


# Placeholder dependency injection function
async def get_session_manager(request: Request) -> SessionDataManager:
    """Get session data manager instance."""
    return request.app.state.resource_manager.session_data_manager


async def get_episodic_memory_manager(request: Request) -> EpisodicMemoryManager:
    """Get episodic memory manager instance."""
    return request.app.state.resource_manager.episodic_memory_manager


async def get_episodic_memory(
    request: Request,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
    episodic_memory_manager: Annotated[
        EpisodicMemoryManager, Depends(get_episodic_memory_manager)
    ],
    session_info: Annotated[SessionInfo, Depends(get_session_info)],
) -> EpisodicMemory:
    """
    Get episodic memory instance.
    
    NOTE: This function is deprecated. Endpoints should use async with
    episodic_memory_manager.open_episodic_memory() directly instead.
    """
    session_key = f"{session_info.org_id}/{session_info.project_id}"
    conf = request.app.state.resource_manager._conf
    await _create_session_if_not_exists(
        session_key=session_key,
        session_manager=session_manager,
        conf=conf,
    )
    # Note: This is a workaround - we can't return from async with
    # This function should not be used in new code
    # Instead, use async with episodic_memory_manager.open_episodic_memory() directly
    raise HTTPException(
        status_code=501,
        detail="get_episodic_memory dependency is deprecated. Use async with open_episodic_memory() directly."
    )


async def _session_exists(
    session_key: str, session_manager: SessionDataManager
) -> bool:
    """Check if a session exists."""
    try:
        await session_manager.get_session_info(session_key=session_key)
    except Exception:
        return False
    return True


async def _create_new_session(
    session_manager: SessionDataManager,
    session_key: str,
    description: str,
    embedder: str,
    reranker: str,
    vector_graph_store: str | None = None,
    llm_model: str | None = None,
    summary_prompt_system: str | None = None,
    summary_prompt_user: str | None = None,
) -> None:
    """Create a new session."""
    # Use provided values or defaults
    vector_store = vector_graph_store or "default_store"
    llm = llm_model or "gpt-4.1"
    
    # Use provided prompts or defaults
    system_prompt = summary_prompt_system or "You are a helpful assistant."
    # summary_prompt_user must contain {episodes}, {summary}, and {max_length} fields
    user_prompt = summary_prompt_user or (
        "Summarize the following episodes:\n{episodes}\n\n"
        "Previous summary:\n{summary}\n\n"
        "Max length: {max_length}"
    )
    
    await session_manager.create_new_session(
        session_key=session_key,
        configuration={},
        param=EpisodicMemoryConf(
            session_key=session_key,
            long_term_memory=LongTermMemoryConf(
                session_id=session_key,
                vector_graph_store=vector_store,
                embedder=embedder,
                reranker=reranker,
            ),
            short_term_memory=ShortTermMemoryConf(
                session_key=session_key,
                llm_model=llm,
                summary_prompt_system=system_prompt,
                summary_prompt_user=user_prompt,
            ),
            long_term_memory_enabled=True,
            short_term_memory_enabled=True,
            enabled=True,
        ),
        description=description,
        metadata={},
    )


async def _create_session_if_not_exists(
    session_key: str,
    session_manager: SessionDataManager,
    conf=None,
) -> None:
    """Create a session if it does not exist."""
    if not await _session_exists(session_key, session_manager):
        # Get default values from config if available
        embedder = "default"
        reranker = "default"
        vector_graph_store = None
        llm_model = None
        summary_prompt_system = None
        summary_prompt_user = None
        
        if conf:
            if conf.episodic_memory:
                if conf.episodic_memory.long_term_memory:
                    if conf.episodic_memory.long_term_memory.embedder:
                        embedder = conf.episodic_memory.long_term_memory.embedder
                    if conf.episodic_memory.long_term_memory.reranker:
                        reranker = conf.episodic_memory.long_term_memory.reranker
                    if conf.episodic_memory.long_term_memory.vector_graph_store:
                        vector_graph_store = conf.episodic_memory.long_term_memory.vector_graph_store
                if conf.episodic_memory.short_term_memory:
                    if conf.episodic_memory.short_term_memory.llm_model:
                        llm_model = conf.episodic_memory.short_term_memory.llm_model
                    if conf.episodic_memory.short_term_memory.summary_prompt_system:
                        summary_prompt_system = conf.episodic_memory.short_term_memory.summary_prompt_system
                    if conf.episodic_memory.short_term_memory.summary_prompt_user:
                        summary_prompt_user = conf.episodic_memory.short_term_memory.summary_prompt_user
            
            # If prompts not found in episodic_memory config, try prompt config
            if not summary_prompt_system and conf.prompt:
                summary_prompt_system = conf.prompt.episode_summary_system_prompt
            if not summary_prompt_user and conf.prompt:
                prompt_user = conf.prompt.episode_summary_user_prompt
                # Ensure the prompt has all required fields: {episodes}, {summary}, {max_length}
                # Check if max_length is missing and add it if needed
                import re
                if "{max_length}" not in prompt_user:
                    # Add max_length field if missing
                    prompt_user = prompt_user + "\n\nMax length: {max_length}"
                summary_prompt_user = prompt_user
        
        await _create_new_session(
            session_manager=session_manager,
            session_key=session_key,
            description="",
            embedder=embedder,
            reranker=reranker,
            vector_graph_store=vector_graph_store,
            llm_model=llm_model,
            summary_prompt_system=summary_prompt_system,
            summary_prompt_user=summary_prompt_user,
        )


@router.post("/projects")
async def create_project(
    spec: CreateProjectSpec,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
) -> None:
    """Create a new project."""
    session_key = f"{spec.org_id}/{spec.project_id}"
    await _create_new_session(
        session_manager=session_manager,
        session_key=session_key,
        description=spec.description,
        embedder=spec.config.embedder,
        reranker=spec.config.reranker,
    )


@router.post("/projects/delete")
async def delete_project(
    spec: DeleteProjectSpec,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
) -> None:
    """Delete a project."""
    session_key = f"{spec.org_id}/{spec.project_id}"
    await session_manager.delete_session(session_key=session_key)


@router.post("/memories")
async def add_memories(
    spec: AddMemoriesSpec,
    request: Request,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
    episodic_memory_manager: Annotated[
        EpisodicMemoryManager, Depends(get_episodic_memory_manager)
    ],
) -> None:
    """Add memories to a project."""
    session_key = f"{spec.org_id}/{spec.project_id}"
    conf = request.app.state.resource_manager._conf
    
    # Create session if it doesn't exist
    await _create_session_if_not_exists(
        session_key=session_key,
        session_manager=session_manager,
        conf=conf,
    )
    
    # Get episodic memory instance using async context manager
    async with episodic_memory_manager.open_episodic_memory(
        session_key=session_key
    ) as episodic_memory:
        for message in spec.messages:
            # Parse timestamp string to datetime if needed
            created_at = message.timestamp
            if isinstance(created_at, str):
                from datetime import datetime
                try:
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except ValueError:
                    created_at = datetime.utcnow()
            
            await episodic_memory.add_memory_episode(
                episode=Episode(
                    uid=str(uuid4()),  # Generate temporary uid, will be replaced on storage
                    content=message.content,
                    session_key=session_key,
                    created_at=created_at,
                    producer_id=message.producer or "",
                    producer_role=message.role or "user",
                    produced_for_id=None,
                    # sequence_num, episode_type, content_type use defaults
                    filterable_metadata=message.metadata,
                )
            )


@router.post("/memories/search")
async def search_memories(
    spec: SearchMemoriesSpec,
    request: Request,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
    episodic_memory_manager: Annotated[
        EpisodicMemoryManager, Depends(get_episodic_memory_manager)
    ],
) -> SearchResult:
    """Search memories in a project."""
    session_key = f"{spec.org_id}/{spec.project_id}"
    conf = request.app.state.resource_manager._conf
    
    # Create session if it doesn't exist
    await _create_session_if_not_exists(
        session_key=session_key,
        session_manager=session_manager,
        conf=conf,
    )
    
    # Get episodic memory instance using async context manager
    async with episodic_memory_manager.open_episodic_memory(
        session_key=session_key
    ) as episodic_memory:
        ret = SearchResult(content={"episodic_memory": [], "semantic_memory": []})
        # Use spec.types (as defined in SearchMemoriesSpec) instead of memory_types
        memory_types = spec.types if spec.types else ["episodic", "semantic"]
        if "episodic" in memory_types:
            episodic_result = await episodic_memory.query_memory(
                query=spec.query,
                limit=spec.top_k,
                property_filter=parse_filter(spec.filter),
            )
            ret.content["episodic_memory"] = episodic_result
        if "semantic" in memory_types:
            # Placeholder for semantic memory search
            ret.content["semantic_memory"] = []
        return ret


@router.post("/memories/list")
async def list_memories(
    spec: ListMemoriesSpec,
    request: Request,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
    episodic_memory_manager: Annotated[
        EpisodicMemoryManager, Depends(get_episodic_memory_manager)
    ],
) -> SearchResult:
    """List memories in a project."""
    session_key = f"{spec.org_id}/{spec.project_id}"
    conf = request.app.state.resource_manager._conf
    
    # Create session if it doesn't exist
    await _create_session_if_not_exists(
        session_key=session_key,
        session_manager=session_manager,
        conf=conf,
    )
    
    # Get episodic memory instance using async context manager
    async with episodic_memory_manager.open_episodic_memory(
        session_key=session_key
    ) as episodic_memory:
        return SearchResult(content={"episodic_memory": [], "semantic_memory": []})


@router.post("/memories/delete")
async def delete_memories(
    spec: DeleteMemoriesSpec,
    request: Request,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
    episodic_memory_manager: Annotated[
        EpisodicMemoryManager, Depends(get_episodic_memory_manager)
    ],
) -> None:
    """Delete memories in a project."""
    session_key = f"{spec.org_id}/{spec.project_id}"
    
    # Get episodic memory instance using async context manager
    async with episodic_memory_manager.open_episodic_memory(
        session_key=session_key
    ) as episodic_memory:
        short_term, long_term, _ = await episodic_memory.query_memory(
            query="",
            property_filter=parse_filter(spec.filter),
        )
        await episodic_memory.delete_episodes(
            episode_ids=[ep.uid for ep in short_term + long_term if ep.uid is not None]
        )


@router.post("/memories/episodic/delete")
async def delete_episodic_memory(
    spec: DeleteEpisodicMemorySpec,
    request: Request,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
    episodic_memory_manager: Annotated[
        EpisodicMemoryManager, Depends(get_episodic_memory_manager)
    ],
) -> None:
    """Delete episodic memories in a project."""
    session_key = f"{spec.org_id}/{spec.project_id}"
    
    # Get episodic memory instance using async context manager
    async with episodic_memory_manager.open_episodic_memory(
        session_key=session_key
    ) as episodic_memory:
        await episodic_memory.delete_episodes(episode_ids=[spec.episodic_id])


@router.post("/memories/semantic/delete")
async def delete_semantic_memory(
    spec: DeleteSemanticMemorySpec,
    request: Request,
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
    episodic_memory_manager: Annotated[
        EpisodicMemoryManager, Depends(get_episodic_memory_manager)
    ],
) -> None:
    """Delete semantic memories in a project."""
    # Placeholder for semantic memory deletion
    pass


def load_v2_api_router(app: FastAPI) -> APIRouter:
    """Load the API v2 router."""
    app.include_router(router, prefix="/api/v2")
    return router
