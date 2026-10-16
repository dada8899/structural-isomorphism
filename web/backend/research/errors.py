"""Safe research errors; no validation inputs or exception strings escape."""
from uuid import uuid4


class ResearchError(Exception):
    def __init__(self, code: str, status: int, message: str, *, retryable: bool = False):
        super().__init__(code)
        self.code, self.status, self.message, self.retryable = code, status, message, retryable

    def body(self):
        return {"error": {"code": self.code, "message": self.message,
                          "retryable": self.retryable,
                          "allowed_next_actions": ["sign_in"] if self.code == "AUTH_REQUIRED" else [],
                          "incident_id": str(uuid4())}}


def not_found():
    return ResearchError("NOT_FOUND", 404, "研究不存在或当前无法访问。")
