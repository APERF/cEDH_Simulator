"""add cards table

Revision ID: a1b2c3d4e5f6
Revises: 2ff418d47614
Create Date: 2026-06-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '2ff418d47614'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scryfall_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('mana_cost', sa.String(length=100), nullable=True),
        sa.Column('cmc', sa.Float(), nullable=True),
        sa.Column('type_line', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('oracle_text', sa.Text(), nullable=True),
        sa.Column('keywords', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('colors', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('color_identity', ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('power', sa.String(length=10), nullable=True),
        sa.Column('toughness', sa.String(length=10), nullable=True),
        sa.Column('image_uri', sa.String(length=500), nullable=True),
        sa.Column('layout', sa.String(length=50), nullable=True),
        sa.Column('last_synced', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scryfall_id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_cards_id'), 'cards', ['id'], unique=False)
    op.create_index(op.f('ix_cards_name'), 'cards', ['name'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_cards_name'), table_name='cards')
    op.drop_index(op.f('ix_cards_id'), table_name='cards')
    op.drop_table('cards')
