"""Entry format. One small JSON file per entry; ids are unique so writers never collide.

Authorship is NOT stored in the entry: the ref path (<user>/<device>) is the authority,
because anyone with push access could otherwise claim any author inside a file.
"""
from __future__ import annotations

import json
import os
import re
import time

ID_RE = re.compile(r"^[0-9a-f]{11}-[0-9a-f]{8}$")
KINDS = ("change", "finding")
PROVENANCE = ("agent-written", "user-edited", "inferred")
BODY_FIELDS = ("summary", "what", "why", "wrong", "fix", "evidence")
INJECTABLE = ("summary", "what", "why", "fix")  # evidence/wrong never enter agent context
MAX_FIELD = 2000
MAX_LIST = 40


def new_id():
    return f"{int(time.time() * 1000):011x}-{os.urandom(4).hex()}"


class Entry:
    """Plain class (not a dataclass): importing dataclasses/inspect costs ~45 ms on every hook invocation."""
    __slots__ = ("id", "kind", "topic", "body", "anchor", "provenance", "captured_via", "supersedes", "display", "created",
                 "redacted", "v")

    def __init__(self, id, kind="finding", topic="", body=None, anchor=None, provenance="agent-written", captured_via="cli",
                 supersedes=None, display="", created="", redacted=False, v=1):
        self.id, self.kind, self.topic = id, kind, topic
        self.body = dict(body or {})
        self.anchor = dict(anchor or {})  # sha tree parent patch_id branch subject date pr paths models dirty
        self.provenance, self.captured_via = provenance, captured_via
        self.supersedes = list(supersedes or [])
        self.display, self.created, self.redacted, self.v = display, created, redacted, v  # created: display only

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    def copy(self, **changes):
        d = self.to_dict()
        d.update(changes)
        return Entry(**d)

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def text(self):
        parts = [self.topic, *(self.body.get(k, "") for k in BODY_FIELDS)]
        a = self.anchor
        parts += [a.get("subject", ""), a.get("branch", ""), *a.get("paths", []), *a.get("models", [])]
        return " ".join(p for p in parts if p)
