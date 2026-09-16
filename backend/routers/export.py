# backend/routers/export.py
"""
Export / import endpoints.

- GET  /api/export/library - Library manifest: what this instance follows (any user)
- GET  /api/export/backup  - Full backup: library + catalog/users/settings (admin)
- POST /api/import         - Apply a document; ?dry_run=true only previews (admin)
"""
from __future__ import annotations
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..deps import get_db
from ..dependencies import require_auth, require_admin
from ..models import User
from ..schemas.export import ExportDocument, ImportResult
from ..services import export as export_svc

logger = logging.getLogger("routers.export")

router = APIRouter(tags=["Export"])


@router.get("/api/export/library", status_code=status.HTTP_200_OK)
def export_library(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Followed artists, downloaded albums and chart subscriptions. Nothing personal."""
    try:
        return export_svc.build_library_export(db)
    except Exception as e:
        logger.exception("export_library failed")
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@router.get("/api/export/backup", status_code=status.HTTP_200_OK)
def export_backup(
    library: bool = Query(True, description="Include followed artists and standalone albums"),
    charts: bool = Query(True, description="Include chart subscriptions"),
    catalog: bool = Query(True, description="Include every artist/album/track row with file paths"),
    users: bool = Query(True, description="Include user accounts (with password hashes)"),
    settings: bool = Query(True, description="Include application settings"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if not any((library, charts, catalog, users, settings)):
        raise HTTPException(status_code=400, detail="Nothing selected to export")
    try:
        return export_svc.build_backup_export(
            db,
            include_library=library,
            include_charts=charts,
            include_catalog=catalog,
            include_users=users,
            include_settings=settings,
        )
    except Exception as e:
        logger.exception("export_backup failed")
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@router.post("/api/import", response_model=ImportResult, status_code=status.HTTP_200_OK)
def import_document(
    doc: ExportDocument,
    dry_run: bool = Query(False, description="Report what would change without applying it"),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ImportResult:
    """
    Apply an export document (library manifest or full backup).

    Existing subscriptions, users and rows are kept; missing ones are created
    and the matching sync/download jobs queued. The dry run walks the same
    code and rolls back, so its summary is what the real run will do.
    """
    if not any((doc.library, doc.catalog, doc.users, doc.settings)):
        raise HTTPException(status_code=400, detail="Document has no importable section")
    try:
        return export_svc.run_import(db, doc, user_id=current_user.id, dry_run=dry_run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("import_document failed")
        raise HTTPException(status_code=500, detail=f"Import failed: {e}")
