from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, event

from .config import ROOT, Settings


def make_engine(settings: Settings):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(URL.create('sqlite', database=str(settings.database_path)), connect_args={'check_same_thread': False})

    @event.listens_for(engine, 'connect')
    def sqlite_pragmas(connection, _):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.execute('PRAGMA busy_timeout=5000')
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.close()

    return engine


def migrate(engine):
    config = Config(str(ROOT / 'backend' / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'backend' / 'migrations'))
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
