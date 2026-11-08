from alembic import context

from backend.app.config import Settings
from backend.app.database import make_engine
from backend.app.models import Base


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get('connection')
if connection is not None:
    run(connection)
else:
    engine = make_engine(Settings())
    with engine.connect() as connection:
        run(connection)
    engine.dispose()
