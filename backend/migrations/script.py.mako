"""${message}

Created ${create_date.strftime("%Y-%m-%d")}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


# Forward only: going back means restoring the copy taken before the
# upgrade (config/db-backups/) and running the previous image.
def upgrade() -> None:
    ${upgrades if upgrades else "pass"}
