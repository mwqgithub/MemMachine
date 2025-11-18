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
from memmachine.episode_store.episode_model import Episode
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
    session_manager: Annotated[SessionDataManager, Depends(get_session_manager)],
    episodic_memory_manager: Annotated[
        EpisodicMemoryManager, Depends(get_episodic_memory_manager)
    ],
    session_info: Annotated[SessionInfo, Depends(get_session_info)],
) -> EpisodicMemory:
    """Get episodic memory instance."""
    # Placeholder for dependency injection

    session_key = f"{session_info.org_id}/{session_info.project_id}"
    await _create_session_if_not_exists(
        session_key=session_key,
        session_manager=session_manager,
    )
    try:
        episodic_memory: EpisodicMemory = next(
            iter(
                await episodic_memory_manager.open_episodic_memory(
                    session_key=session_key
                )
            )
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="Episode memory not found") from e
    return episodic_memory


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
) -> None:
    """Create a new session."""
    await session_manager.create_new_session(
        session_key=session_key,
        configuration={},
        param=EpisodicMemoryConf(
            session_key=session_key,
            long_term_memory=LongTermMemoryConf(
                session_id=session_key,
                vector_graph_store="default_store",
                embedder=embedder,
                reranker=reranker,
            ),
            short_term_memory=ShortTermMemoryConf(
                session_key=session_key,
                llm_model="gpt-4.1",
                summary_prompt_system="You are a helpful assistant.",
                summary_prompt_user="Summarize the following content:",
            ),
            long_term_memory_enabled=True,
            short_term_memory_enabled=True,
            enabled=True,
        ),
        description=description,
        metadata={},
    )


async def _create_session_if_not_exists(
    session_key: str, session_manager: SessionDataManager
) -> None:
    """Create a session if it does not exist."""
    if not await _session_exists(session_key, session_manager):
        await _create_new_session(
            session_manager=session_manager,
            session_key=session_key,
            description="",
            embedder="default",
            reranker="default",
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
    episodic_memory: Annotated[EpisodicMemory, Depends(get_episodic_memory)],
) -> None:
    """Add memories to a project."""
    session_key = f"{spec.org_id}/{spec.project_id}"

    for message in spec.messages:
        await episodic_memory.add_memory_episode(
            episode=Episode(
                content=message.content,
                session_key=session_key,
                created_at=message.timestamp,
                producer_id=message.producer,
                producer_role=message.role,
                produced_for_id=None,
                sequence_num=None,
                episode_type=None,
                content_type=None,
                filterable_metadata=message.metadata,
            )
        )


@router.post("/memories/search")
async def search_memories(
    spec: SearchMemoriesSpec,
    episodic_memory: Annotated[EpisodicMemory, Depends(get_episodic_memory)],
) -> SearchResult:
    """Search memories in a project."""
    ret = SearchResult(content={"episodic_memory": [], "semantic_memory": []})
    if "episodic" in spec.memory_types:
        episodic_result = await episodic_memory.query_memory(
            query=spec.query,
            limit=spec.top_k,
            property_filter=parse_filter(spec.filter),
        )
        ret.content["episodic_memory"] = episodic_result
    if "semantic" in spec.memory_types:
        # Placeholder for semantic memory search
        ret.content["semantic_memory"] = []
    return ret


@router.post("/memories/list")
async def list_memories(
    spec: ListMemoriesSpec,
    episodic_memory: Annotated[EpisodicMemory, Depends(get_episodic_memory)],
) -> None:
    """List memories in a project."""
    return SearchResult(content={"episodic_memory": [], "semantic_memory": []})


@router.post("/memories/delete")
async def delete_memories(
    spec: DeleteMemoriesSpec,
    episodic_memory: Annotated[EpisodicMemory, Depends(get_episodic_memory)],
) -> None:
    """Delete memories in a project."""
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
    episodic_memory: Annotated[EpisodicMemory, Depends(get_episodic_memory)],
) -> None:
    """Delete episodic memories in a project."""
    await episodic_memory.delete_episodes(episode_ids=[spec.episodic_id])


@router.post("/memories/semantic/delete")
async def delete_semantic_memory(
    spec: DeleteSemanticMemorySpec,
    episodic_memory: Annotated[EpisodicMemory, Depends(get_episodic_memory)],
) -> None:
    """Delete semantic memories in a project."""
    # Placeholder for semantic memory deletion


def load_v2_api_router(app: FastAPI) -> APIRouter:
    """Load the API v2 router."""
    app.include_router(router, prefix="/api/v2")
    return router
