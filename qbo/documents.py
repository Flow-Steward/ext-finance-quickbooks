"""Host-granted document inputs and outputs; no arbitrary paths or download URLs."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from typing import Any

from flowsteward_extension_sdk import ArtifactAccessError, read_artifact_bytes, write_artifact_bytes

from qbo.commands import Plan
from qbo.transport import Transport
from qbo.validation import FILE_LIMIT, Failure, require, text


ALLOWED_CONTENT_TYPES = frozenset(
    {
        "application/postscript",
        "text/csv",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/gif",
        "image/jpeg",
        "image/jpg",
        "application/vnd.oasis.opendocument.spreadsheet",
        "application/pdf",
        "image/png",
        "text/rtf",
        "image/tif",
        "image/tiff",
        "text/plain",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/xml",
    }
)


def upload_attachment(
    payload: dict[str, Any], args: dict[str, Any], plan: Plan, transport: Transport
) -> Any:
    data = dict(plan.body or {})
    filename = text(data.get("FileName"), 255)
    require(
        "/" not in filename and "\\" not in filename and '"' not in filename,
        "FileName must be a plain filename.",
    )
    mime = data.get("ContentType", "application/octet-stream")
    require(mime in ALLOWED_CONTENT_TYPES, "Supply a QuickBooks-supported ContentType.")
    try:
        raw = read_artifact_bytes(
            payload,
            binding_key="attachment_input",
            timeout_seconds=transport.config["request_timeout_seconds"],
        )
    except (ArtifactAccessError, OSError, ValueError):
        raise Failure(
            "artifact_unavailable", "The approved attachment input is unavailable."
        ) from None
    require(
        0 < len(raw) <= FILE_LIMIT, "Attachment exceeds the supported size.", "response_too_large"
    )
    boundary = "fs-qbo-" + hashlib.sha256(raw).hexdigest()[:32]
    require(boundary.encode() not in raw, "Attachment contains a multipart boundary collision.")
    data["ContentType"] = mime
    # ensure_ascii prevents header injection through non-ASCII filename metadata.
    metadata = json.dumps(data, ensure_ascii=True, allow_nan=False).encode()
    safe_header_name = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file_metadata_01"\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()
        + metadata
        + f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file_content_01"; filename="{safe_header_name}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
        + raw
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return transport.request(
        replace(plan, path="/upload", body=None),
        body=body,
        content_type="multipart/form-data; boundary=" + boundary,
    )


def save_pdf(payload: dict[str, Any], raw: bytes) -> dict[str, Any]:
    try:
        written = write_artifact_bytes(
            payload, raw, binding_key="pdf_artifact_handle", content_type="application/pdf"
        )
        handle = written.get("artifact_handle")
        require(
            isinstance(handle, str) and bool(handle),
            "Invalid PDF output artifact.",
            "artifact_unavailable",
        )
        return {"pdf_artifact_handle": handle}
    except (ArtifactAccessError, OSError, ValueError):
        raise Failure("artifact_unavailable", "The approved PDF output is unavailable.") from None
