##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Add shared_username_from_pgadmin to the server table

A shared server can be set to connect every non-owner as their own
pgAdmin username. This adds the flag that holds that choice. It lives on
the owner's server only: the username is worked out at connect time, so
nothing is added to the sharedserver table.

Revision ID: server_shared_username_from_pgadmin
Revises: server_passexec_name
Create Date: 2026-11-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'server_shared_username_from_pgadmin'
down_revision = 'server_passexec_name'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not inspector.has_table('server'):
        return
    existing_cols = {c['name'] for c in inspector.get_columns('server')}
    if 'shared_username_from_pgadmin' in existing_cols:
        return
    with op.batch_alter_table('server') as batch_op:
        batch_op.add_column(
            sa.Column('shared_username_from_pgadmin', sa.Boolean(),
                      nullable=False, server_default=sa.false()))


def downgrade():
    # pgAdmin only upgrades, downgrade not implemented.
    pass
