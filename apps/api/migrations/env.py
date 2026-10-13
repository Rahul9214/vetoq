from alembic import context

from vetoq.config import Settings
from vetoq.db import engine_for

with engine_for(Settings()).connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
