"""Create all tables from SQLAlchemy metadata (initial institutional schema)."""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260216_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    from app.db.base import Base

    import app.models  # noqa: F401

    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    from app.db.base import Base

    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=bind)
