"""fix booking form migration

Revision ID: 77073d810955
Revises: 11ea2e6efa95
Create Date: 2025-08-11 22:05:08.090863

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '77073d810955'
down_revision = '11ea2e6efa95'
branch_labels = None
depends_on = None


def upgrade():
    # Fix for the problematic table drop
    try:
        op.drop_table('_alembic_tmp_booking_form')
    except Exception:
        # Table doesn't exist, that's fine - continue without error
        pass


def downgrade():
    pass
