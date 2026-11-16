"""Append-only JSONL transcripts, and resuming from them."""

from pyharnx.session.recorder import SessionRecorder, start_recorder
from pyharnx.session.resume import ResumedSession, ResumeError, resume, trim_to_resumable
from pyharnx.session.store import (
    find_session,
    latest_session,
    list_sessions,
    new_session_id,
    project_directory,
    project_slug,
    session_path,
)
from pyharnx.session.transcript import (
    RecordedMessage,
    RecordedRequest,
    Rewrite,
    Segment,
    SessionContext,
    SessionHeader,
    Transcript,
    TranscriptError,
    TranscriptWriter,
    read_transcript,
    recorded_requests,
)

__all__ = [
    "RecordedMessage",
    "RecordedRequest",
    "ResumeError",
    "ResumedSession",
    "Rewrite",
    "Segment",
    "SessionContext",
    "SessionHeader",
    "SessionRecorder",
    "Transcript",
    "TranscriptError",
    "TranscriptWriter",
    "find_session",
    "latest_session",
    "list_sessions",
    "new_session_id",
    "project_directory",
    "project_slug",
    "read_transcript",
    "recorded_requests",
    "resume",
    "session_path",
    "start_recorder",
    "trim_to_resumable",
]
