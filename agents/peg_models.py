# peg_models.py
from uagents import Model

# ========== Internal (responder <-> monitor) ==========
class PegSnapshotRequest(Model):
    corr_id: str

class PegSnapshotResponse(Model):
    corr_id: str
    ok: bool
    payload_json: str  # JSON string of the latest snapshot

# ========== Public (client <-> responder) ==========
class PegCheckRequest(Model):
    """External request asking for the latest peg snapshot."""
    note: str = "latest"

class PegCheckResponse(Model):
    ok: bool
    payload_json: str  # JSON string of the latest snapshot (or error payload)