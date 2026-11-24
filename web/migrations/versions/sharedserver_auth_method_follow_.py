##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Let a non-owner's shared server follow the owner's auth_method

A NULL auth_method on a sharedserver row means "use the owner's server
authentication method". Existing rows keep the method they store, since a
default that was forced on them cannot be told apart from a deliberate
choice.

Revision ID: sharedserver_auth_method_follow
Revises: server_auth_method
Create Date: 2026-11-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'sharedserver_auth_method_follow'
down_revision = 'server_auth_method'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table('sharedserver'):
        return
    with op.batch_alter_table('sharedserver') as batch_op:
        batch_op.alter_column(
            'auth_method', existing_type=sa.String(length=32),
            nullable=True, server_default=None)


def downgrade():
    # pgAdmin only upgrades, downgrade not implemented.
    pass
