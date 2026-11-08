"""Initial frozen standalone schema derived from original content migrations."""
from alembic import op
import sqlalchemy as sa
revision = 'content_0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('campaigns', sa.Column('id', sa.String(36), primary_key=True), sa.Column('name', sa.String(120), nullable=False), sa.Column('snapshot', sa.JSON(), nullable=False), sa.Column('created_at', sa.String(40), nullable=False))
    op.create_index('ix_campaigns_created_at', 'campaigns', ['created_at'])
    op.create_table('research_runs', sa.Column('id', sa.String(36), primary_key=True), sa.Column('origin', sa.String(10), nullable=False), sa.Column('topic', sa.String(5000), nullable=False), sa.Column('snapshot', sa.JSON(), nullable=False), sa.Column('created_at', sa.String(40), nullable=False))
    op.create_index('ix_research_runs_created_at', 'research_runs', ['created_at'])
    op.create_table('generation_jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('report_id', sa.String(36), sa.ForeignKey('research_runs.id'), nullable=False),
        sa.Column('campaign_id', sa.String(36), sa.ForeignKey('campaigns.id')),
        sa.Column('family_id', sa.String(36), nullable=False),
        sa.Column('parent_job_id', sa.String(36), sa.ForeignKey('generation_jobs.id')),
        sa.Column('idempotency_key', sa.String(128), nullable=False, unique=True),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('current_stage', sa.String(40), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False),
        sa.Column('checkpoint', sa.JSON(), nullable=False),
        sa.Column('stages', sa.JSON(), nullable=False),
        sa.Column('results', sa.JSON(), nullable=False),
        sa.Column('error', sa.String(500)),
        sa.Column('created_at', sa.String(40), nullable=False))
    for field in ('family_id', 'status', 'created_at'):
        op.create_index('ix_generation_jobs_' + field, 'generation_jobs', [field])
    op.create_table('assets', sa.Column('id',sa.String(36),primary_key=True),sa.Column('storage_key',sa.String(200),unique=True,nullable=False),sa.Column('checksum',sa.String(64),nullable=False),sa.Column('origin',sa.String(40),nullable=False),sa.Column('width',sa.Integer(),nullable=False),sa.Column('height',sa.Integer(),nullable=False),sa.Column('metadata_json',sa.JSON(),nullable=False))
    op.create_table('content_items',sa.Column('id',sa.String(36),primary_key=True),sa.Column('family_id',sa.String(36),nullable=False),sa.Column('concept_index',sa.Integer(),nullable=False),sa.Column('current_version_id',sa.String(36)),sa.UniqueConstraint('family_id','concept_index'))
    op.create_table('content_versions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('item_id',sa.String(36),sa.ForeignKey('content_items.id'),nullable=False),sa.Column('job_id',sa.String(36),sa.ForeignKey('generation_jobs.id'),nullable=False),sa.Column('version_number',sa.Integer(),nullable=False),sa.Column('snapshot',sa.JSON(),nullable=False),sa.Column('payload_digest',sa.String(64),nullable=False),sa.Column('created_at',sa.String(40),nullable=False),sa.UniqueConstraint('item_id','version_number'),sa.UniqueConstraint('item_id','job_id'))
    for action in ('UPDATE', 'DELETE'):
        op.execute(f"CREATE TRIGGER content_versions_no_{action.lower()} BEFORE {action} ON content_versions BEGIN SELECT RAISE(ABORT, 'Content versions are immutable'); END")
    op.add_column('content_items', sa.Column('trashed_at', sa.String(40), nullable=True))
    op.create_index('ix_content_items_trashed_at', 'content_items', ['trashed_at'])
    op.add_column('content_items', sa.Column('deleted_at', sa.String(40), nullable=True))
    op.execute('DROP TRIGGER content_versions_no_delete')
    op.execute("CREATE TRIGGER content_versions_no_delete BEFORE DELETE ON content_versions WHEN NOT EXISTS (SELECT 1 FROM content_items WHERE id=OLD.item_id AND trashed_at IS NOT NULL AND deleted_at IS NOT NULL) BEGIN SELECT RAISE(ABORT, 'Content versions are immutable'); END")

def downgrade():
    raise RuntimeError('Destructive downgrade is not supported; choose a fresh standalone data directory.')
