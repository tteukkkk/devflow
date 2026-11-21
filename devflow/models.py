from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from devflow.db import Base

def now(): return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    avatar_color: Mapped[str] = mapped_column(String(20), default='#7957d5')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Workspace(Base):
    __tablename__ = 'workspaces'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Membership(Base):
    __tablename__ = 'memberships'
    __table_args__ = (UniqueConstraint('workspace_id','user_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(20), default='member')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Project(Base):
    __tablename__ = 'projects'
    __table_args__ = (UniqueConstraint('workspace_id','key'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(12))
    description: Mapped[str] = mapped_column(Text, default='')
    color: Mapped[str] = mapped_column(String(20), default='#9061f9')
    icon: Mapped[str] = mapped_column(String(16), default='◈')
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = (UniqueConstraint('project_id','number'),Index('ix_task_project_status','project_id','status'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id',ondelete='CASCADE'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(24), default='todo')
    priority: Mapped[str] = mapped_column(String(20), default='medium')
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey('users.id',ondelete='SET NULL'), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

class Label(Base):
    __tablename__ = 'labels'
    __table_args__ = (UniqueConstraint('workspace_id','name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(40))
    color: Mapped[str] = mapped_column(String(20), default='#8b5cf6')

class TaskLabel(Base):
    __tablename__ = 'task_labels'
    __table_args__ = (UniqueConstraint('task_id','label_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id',ondelete='CASCADE'), index=True)
    label_id: Mapped[int] = mapped_column(ForeignKey('labels.id',ondelete='CASCADE'), index=True)

class Comment(Base):
    __tablename__ = 'comments'
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id',ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Checklist(Base):
    __tablename__ = 'checklists'
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id',ondelete='CASCADE'), index=True)
    text: Mapped[str] = mapped_column(String(240))
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

class Activity(Base):
    __tablename__ = 'activities'
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    project_id: Mapped[int | None] = mapped_column(ForeignKey('projects.id',ondelete='SET NULL'),nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey('tasks.id',ondelete='SET NULL'),nullable=True)
    verb: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(250),default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Invitation(Base):
    __tablename__ = 'invitations'
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'), index=True)
    email: Mapped[str] = mapped_column(String(180))
    role: Mapped[str] = mapped_column(String(20), default='member')
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime,nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(String(300),default='')
    task_id: Mapped[int | None] = mapped_column(ForeignKey('tasks.id',ondelete='CASCADE'),nullable=True)
    read: Mapped[bool] = mapped_column(Boolean,default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class ProjectSequence(Base):
    __tablename__='project_sequences'
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id',ondelete='CASCADE'),primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer,default=0)

class GitHubIntegration(Base):
    __tablename__='github_integrations'
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id',ondelete='CASCADE'),primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey('workspaces.id',ondelete='CASCADE'),index=True)
    repository: Mapped[str] = mapped_column(String(220))

class ImportedGitHubIssue(Base):
    __tablename__='imported_github_issues'
    __table_args__=(UniqueConstraint('project_id','issue_number'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey('projects.id',ondelete='CASCADE'),index=True)
    issue_number: Mapped[int] = mapped_column(Integer)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id',ondelete='CASCADE'),unique=True)
