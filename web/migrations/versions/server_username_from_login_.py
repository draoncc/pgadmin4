##########################################################################
#
# pgAdmin 4 - PostgreSQL Tools
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Add username_from_login to the server and sharedserver tables

With "Username from login" on, the database username is taken from the
pgAdmin user's OAuth2 login when connecting. On a server, true is on and
false or NULL is off. On a non-owner's sharedserver row, NULL follows the
owner's value and true or false is the non-owner's own choice. Every
existing server stays off.

Revision ID: server_username_from_login
Revises: sharedserver_auth_method_follow
Create Date: 2026-11-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'server_username_from_login'
down_revision = 'sharedserver_auth_method_follow'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    for table in ('server', 'sharedserver'):
        if not inspector.has_table(table):
            continue
        existing_cols = {c['name'] for c in inspector.get_columns(table)}
        if 'username_from_login' in existing_cols:
            continue
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(
                sa.Column('username_from_login', sa.Boolean(),
                          nullable=True))


def downgrade():
    # pgAdmin only upgrades, downgrade not implemented.
    pass
