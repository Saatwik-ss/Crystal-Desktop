from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey, JSON, Boolean
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Repository(Base):
    """Repository / Project metadata"""
    __tablename__ = "repositories"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    repo_metadata = Column("metadata", JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RepositoryFile(Base):
    """File metadata in repository"""
    __tablename__ = "repository_files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    path = Column(String, nullable=False)
    language = Column(String)
    content_hash = Column(String)
    ast_data = Column(JSON)
    size = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class IndexingStatus(Base):
    """Tracking indexing status"""
    __tablename__ = "indexing_status"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    status = Column(String)  # "pending", "indexing", "completed", "failed"
    files_processed = Column(Integer, default=0)
    total_files = Column(Integer, default=0)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CodeSnapshot(Base):
    """Version control - snapshots of repository state"""
    __tablename__ = "code_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    repository_id = Column(String, ForeignKey("repositories.id"), nullable=False)
    description = Column(String)
    changes = Column(JSON)  # List of file changes
    diff = Column(Text)  # Unified diff
    created_at = Column(DateTime, default=datetime.utcnow)

class ChatSession(Base):
    """Persistent chat session belonging to a repository/project"""
    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True)
    project_id = Column(String, ForeignKey("repositories.id"), nullable=True, index=True)
    title = Column(String, nullable=False, default="New Chat")
    model = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ChatMessage(Base):
    """Persistent chat message in a session"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False, default="")
    thought = Column(Text, nullable=True)
    type = Column(String, default="message")  # "message", "planning", "tool_use", "tool_result", "edit_proposal", "error"
    plan = Column(JSON, nullable=True)
    tool_calls = Column(JSON, nullable=True)
    terminal_logs = Column(JSON, nullable=True)
    proposed_edits = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

class UserSetting(Base):
    """Key-value persistent user settings (active project, active model, etc.)"""
    __tablename__ = "user_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Ticket(Base):
    """Engineering task/ticket driving agent work and branches"""
    __tablename__ = "tickets"

    id = Column(String(36), primary_key=True)
    project_id = Column(String, ForeignKey("repositories.id"), nullable=False, index=True)
    github_issue_number = Column(Integer, nullable=True, index=True)
    github_issue_url = Column(String, nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(30), default="todo")  # todo, in_progress, in_verification, in_review, done, blocked
    priority = Column(String(20), default="medium")  # low, medium, high, critical
    assignee_type = Column(String(20), default="unassigned")  # human, agent, unassigned
    assignee_id = Column(String(100), nullable=True)
    reviewer_id = Column(String(100), nullable=True)
    active_branch = Column(String(255), nullable=True)
    active_worktree = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TicketAcceptanceCriteria(Base):
    """Executable acceptance criteria for a ticket"""
    __tablename__ = "ticket_criteria"

    id = Column(String(36), primary_key=True)
    ticket_id = Column(String(36), ForeignKey("tickets.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    criterion_type = Column(String(30), default="automated_test")  # automated_test, manual_review, repro_check
    verification_command = Column(String(500), nullable=True)
    is_satisfied = Column(Boolean, default=False)
    evidence_event_id = Column(String(36), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ChangeLedgerEvent(Base):
    """Immutable, append-only record of a meaningful engineering action or patch"""
    __tablename__ = "change_ledger_events"

    id = Column(String(36), primary_key=True)
    project_id = Column(String, ForeignKey("repositories.id"), nullable=False, index=True)
    ticket_id = Column(String(36), nullable=True, index=True)
    actor_type = Column(String(20), default="agent")  # human, agent, system, reviewer
    actor_id = Column(String(100), nullable=False)
    branch = Column(String(255), nullable=True)
    worktree_path = Column(String(500), nullable=True)
    event_type = Column(String(30), nullable=False)  # edit, commit, test_run, hypothesis_eval, pr_opened, review, merged, reverted
    summary = Column(Text, nullable=False)
    files_changed = Column(JSON, nullable=True)
    diff_stats = Column(JSON, nullable=True)
    diff_patch = Column(Text, nullable=True)
    verification_status = Column(String(20), default="not_run")  # not_run, pending, passed, failed
    verification_details = Column(JSON, nullable=True)
    causal_metadata = Column(JSON, nullable=True)
    github_references = Column(JSON, nullable=True)
    cost_metrics = Column(JSON, nullable=True)
    parent_event_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

