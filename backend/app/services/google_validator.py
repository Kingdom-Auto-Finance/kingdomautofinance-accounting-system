"""
Google API validation service.

Validates that Google Sheets and Drive resources are accessible
before saving configuration settings.
"""

import sys
from pathlib import Path

# Add src directory to path to import gutils
src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

try:
    from gutils import get_gspread_client, get_drive_service
except ImportError as e:
    print(f"Warning: Could not import gutils: {e}")
    get_gspread_client = None
    get_drive_service = None


def validate_sheet_access(sheet_id: str) -> bool:
    """
    Validate that a Google Sheet is accessible.

    Args:
        sheet_id: Google Sheet ID to validate

    Returns:
        True if accessible

    Raises:
        Exception: If sheet is not accessible or doesn't exist
    """
    if get_gspread_client is None:
        raise ImportError("gutils.get_gspread_client not available")

    try:
        # Get authenticated gspread client
        gc = get_gspread_client()

        # Attempt to open the sheet
        sheet = gc.open_by_key(sheet_id)

        # Try to access sheet title to ensure it's readable
        _ = sheet.title

        return True

    except Exception as e:
        error_msg = str(e)

        # Provide user-friendly error messages
        if "404" in error_msg or "not found" in error_msg.lower():
            raise ValueError(f"Google Sheet not found. Please check the Sheet ID: {sheet_id}")
        elif "403" in error_msg or "permission" in error_msg.lower():
            raise ValueError(
                f"Permission denied accessing Google Sheet. "
                f"Please ensure the service account has access to this sheet: {sheet_id}"
            )
        else:
            raise ValueError(f"Failed to access Google Sheet: {error_msg}")


def validate_folder_access(folder_id: str) -> bool:
    """
    Validate that a Google Drive folder is accessible.

    Args:
        folder_id: Google Drive folder ID to validate

    Returns:
        True if accessible

    Raises:
        Exception: If folder is not accessible or doesn't exist
    """
    if get_drive_service is None:
        raise ImportError("gutils.get_drive_service not available")

    try:
        # Get authenticated Drive service
        service = get_drive_service()

        # Attempt to get folder metadata
        folder = service.files().get(
            fileId=folder_id,
            fields='id, name, mimeType'
        ).execute()

        # Verify it's actually a folder
        if folder.get('mimeType') != 'application/vnd.google-apps.folder':
            raise ValueError(f"ID {folder_id} is not a folder (it's a {folder.get('mimeType', 'unknown type')})")

        # Try to list contents to ensure we have read access
        service.files().list(
            q=f"'{folder_id}' in parents",
            pageSize=1,
            fields='files(id, name)'
        ).execute()

        return True

    except Exception as e:
        error_msg = str(e)

        # Provide user-friendly error messages
        if "404" in error_msg or "not found" in error_msg.lower():
            raise ValueError(f"Google Drive folder not found. Please check the Folder ID: {folder_id}")
        elif "403" in error_msg or "permission" in error_msg.lower():
            raise ValueError(
                f"Permission denied accessing Google Drive folder. "
                f"Please ensure the service account has access to this folder: {folder_id}"
            )
        else:
            raise ValueError(f"Failed to access Google Drive folder: {error_msg}")
