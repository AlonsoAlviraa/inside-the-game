"""Five-agent commentary room orchestrated with Microsoft Agent Framework.

Ingest -> (Interpret || Salience scout) -> Explain -> Render -> Personalise
"""
from .state import Batch, RoomState, ViewerProfile, ViewerMemory, CARD_SCHEMA, validate_card
from .workflow import CommentaryRoom

__all__ = ["Batch", "RoomState", "ViewerProfile", "ViewerMemory", "CARD_SCHEMA", "validate_card", "CommentaryRoom"]
