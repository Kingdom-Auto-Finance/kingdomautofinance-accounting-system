"""
Settings API endpoints.

Provides REST API for managing system configuration settings.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.settings_service import settings_manager
from app.services.google_validator import validate_sheet_access, validate_folder_access


router = APIRouter()


# Request/Response Models
class UpdateSettingRequest(BaseModel):
    value: str
    type: Optional[str] = None  # 'sheet' or 'folder'


class SettingResponse(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    category: str


class MessageResponse(BaseModel):
    message: str


# Valid setting keys (whitelist)
VALID_SETTING_KEYS = {
    "SOURCE_PAYMENTS_SHEET_ID",
    "AMORTIZATION_SCHEDULES_FOLDER_ID"
}


@router.get("/")
async def get_settings(category: Optional[str] = None):
    """
    Get all settings, optionally filtered by category.

    Args:
        category: Optional category to filter by (e.g., 'google_integration')

    Returns:
        List of settings with metadata
    """
    try:
        settings = settings_manager.get_all_settings(category)
        return {
            "data": settings,
            "count": len(settings)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{key}")
async def get_setting(key: str):
    """
    Get a specific setting by key.

    Args:
        key: Setting key to retrieve

    Returns:
        Setting with value and metadata
    """
    # Validate key
    if key not in VALID_SETTING_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid setting key: {key}. Valid keys are: {', '.join(VALID_SETTING_KEYS)}"
        )

    try:
        # Get all settings to find the one with metadata
        all_settings = settings_manager.get_all_settings()
        setting = next((s for s in all_settings if s["key"] == key), None)

        if not setting:
            # Setting doesn't exist in DB yet, return current value from env/default
            value = settings_manager.get_setting(key)
            return {
                "key": key,
                "value": value,
                "description": None,
                "category": "google_integration"
            }

        return setting
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{key}")
async def update_setting(key: str, request: UpdateSettingRequest):
    """
    Update a setting value.

    Validates URL/ID format, extracts ID if URL provided,
    and tests Google API access before saving.

    Args:
        key: Setting key to update
        request: Update request with value and optional type

    Returns:
        Updated setting
    """
    # Validate key
    if key not in VALID_SETTING_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid setting key: {key}. Valid keys are: {', '.join(VALID_SETTING_KEYS)}"
        )

    try:
        # Determine type from key if not provided
        if request.type:
            setting_type = request.type
        else:
            # Infer type from key name
            if "SHEET" in key:
                setting_type = "sheet"
            elif "FOLDER" in key:
                setting_type = "folder"
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot infer type from key '{key}'. Please provide 'type' parameter."
                )

        # Extract ID from URL or validate direct ID
        try:
            extracted_id = settings_manager.extract_google_id(request.value, setting_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Validate Google API access
        try:
            if setting_type == "sheet":
                validate_sheet_access(extracted_id)
            elif setting_type == "folder":
                validate_folder_access(extracted_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to validate Google {setting_type} access: {str(e)}"
            )

        # Update setting in database
        result = settings_manager.set_setting(key, extracted_id)

        # Clear cache to ensure new value is used immediately
        settings_manager.clear_cache()

        return {
            **result,
            "message": "Setting updated successfully"
        }

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_settings_cache():
    """
    Manually clear the settings cache.

    Forces settings to be reloaded from database on next access.

    Returns:
        Success message
    """
    try:
        settings_manager.clear_cache()
        return {"message": "Settings cache cleared successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
