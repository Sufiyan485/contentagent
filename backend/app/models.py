from datetime import datetime, timezone


from uuid import uuid4


from sqlalchemy import JSON, String, Text, ForeignKey, Integer, UniqueConstraint


from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = 'campaigns'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)


class ResearchRun(Base):
    __tablename__ = 'research_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    origin: Mapped[str] = mapped_column(String(10))
    topic: Mapped[str] = mapped_column(String(5000))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)


class GenerationJob(Base):
    __tablename__ = 'generation_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    report_id: Mapped[str] = mapped_column(ForeignKey('research_runs.id'))
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey('campaigns.id'), nullable=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_job_id: Mapped[str | None] = mapped_column(ForeignKey('generation_jobs.id'), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    current_stage: Mapped[str] = mapped_column(String(40), default='validate')
    snapshot: Mapped[dict] = mapped_column(JSON)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    stages: Mapped[list] = mapped_column(JSON, default=list)
    results: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso, index=True)


class Asset(Base):
    __tablename__ = 'assets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    checksum: Mapped[str] = mapped_column(String(64))
    origin: Mapped[str] = mapped_column(String(40))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    metadata_json: Mapped[dict] = mapped_column(JSON)


class ContentItem(Base):
    __tablename__ = 'content_items'
    __table_args__ = (UniqueConstraint('family_id', 'concept_index'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    family_id: Mapped[str] = mapped_column(String(36))
    concept_index: Mapped[int] = mapped_column(Integer)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    trashed_at: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    deleted_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class ContentVersion(Base):
    __tablename__ = 'content_versions'
    __table_args__ = (UniqueConstraint('item_id', 'version_number'), UniqueConstraint('item_id', 'job_id'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    item_id: Mapped[str] = mapped_column(ForeignKey('content_items.id'))
    job_id: Mapped[str] = mapped_column(ForeignKey('generation_jobs.id'))
    version_number: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    payload_digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)

