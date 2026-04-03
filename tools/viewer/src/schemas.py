from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class SessionMetadata(BaseModel):
    key: str
    filename: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    size_bytes: int = 0
    channel: Optional[str] = None
    agent: Optional[str] = None

class Message(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    reasoning: Optional[str] = None

class SessionDetail(BaseModel):
    metadata: Dict[str, Any]
    messages: List[Dict[str, Any]]
    total: int

class SessionListResponse(BaseModel):
    sessions: List[SessionMetadata]
    total: int

class DockerLogsResponse(BaseModel):
    logs: str
    container: str

class AgentInfo(BaseModel):
    """Agent metadata exposed to frontend. (fork-local)"""
    name: str
    container_name: str

class AppConfig(BaseModel):
    sessions_dir: str
    container_name: str
    version: str = "2.0.0-modular"
    pool_mode: bool = False
    agents: list[AgentInfo] = []


class SubagentUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0
    requests: int = 0


class SubagentToolCall(BaseModel):
    name: str
    arguments: str = ""
    result: str = ""


class SubagentIteration(BaseModel):
    model_config = {"protected_namespaces": ()}

    number: int
    model_response: Optional[str] = None
    tool_calls: List[SubagentToolCall] = []
    usage: Optional[SubagentUsage] = None


class SubagentSummary(BaseModel):
    filename: str
    task_id: str = ""
    label: str = ""
    status: str = "unknown"
    started: Optional[str] = None
    finished: Optional[str] = None
    duration: Optional[str] = None
    usage: Optional[SubagentUsage] = None
    agent: Optional[str] = None


class SubagentDetail(BaseModel):
    filename: str
    task_id: str = ""
    label: str = ""
    status: str = "unknown"
    started: Optional[str] = None
    finished: Optional[str] = None
    duration: Optional[str] = None
    task: str = ""
    iterations: List[SubagentIteration] = []
    final_result: str = ""
    usage: Optional[SubagentUsage] = None


class SubagentListResponse(BaseModel):
    subagents: List[SubagentSummary]
    total: int
