"""
FastAPI route handlers for the Google Reviews application.
"""

from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from pydantic import BaseModel, Field

from app.config import API_SECRET, WEBHOOK_URL
from app.services.common.logger import get_logger
from app.services.persistence.repositories.draft_repository import (
    get_all_pending_replies, get_stats, get_pending_reply,
    mark_posted, mark_rejected
)
from app.services.jobs.polling.review_poller import polling_loop
from app.services.external.google.posting import post_reply

router = APIRouter()
logger = get_logger(__name__)


async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid API key")


class EditRequest(BaseModel):
    text: str = Field(..., min_length=10)


@router.get("/health")
async def health(request: Request):
    """Health check endpoint for Cloud Run."""
    creds = request.app.state.creds
    locations = request.app.state.locations
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "authenticated": creds is not None,
        "locations_loaded": len(locations),
    }


@router.get("/stats", dependencies=[Depends(verify_api_key)])
async def stats():
    """Return database statistics."""
    db_stats = get_stats()
    return {
        "status": "ok",
        "database": db_stats,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/reviews", dependencies=[Depends(verify_api_key)])
async def get_all_reviews_endpoint():
    """Get all pending reviews waiting for owner approval."""
    pending = get_all_pending_replies("pending")
    return {
        "status": "ok",
        "count": len(pending),
        "pending_reviews": pending,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/telegram")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint.
    Active when WEBHOOK_URL is set; returns early in polling mode.
    """
    if not WEBHOOK_URL:
        return {"status": "ok", "message": "polling mode active"}

    from app.services.external.telegram.bot import process_webhook_update
    data = await request.json()
    await process_webhook_update(data)
    return {"ok": True}


@router.post("/poll")
async def manual_poll(request: Request):
    """Trigger polling immediately (for testing)."""
    try:
        creds = request.app.state.creds
        locations = request.app.state.locations
        polling_loop(creds, locations)
        return {"status": "ok", "message": "Polling triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drafts/{review_id}/approve", dependencies=[Depends(verify_api_key)])
async def approve_draft(review_id: str, request: Request):
    """Approve a pending draft and post it to Google My Business."""
    if not review_id.strip():
        raise HTTPException(status_code=400, detail="review_id must not be empty")

    try:
        draft = get_pending_reply(review_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        if draft["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Can only approve pending drafts, this is {draft['status']}"
            )

        creds = request.app.state.creds
        location_name = draft["location_name"]
        reply_text = draft["draft_reply"]

        result = post_reply(creds, location_name, review_id, reply_text)
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Failed to post reply to Google My Business"
            )

        mark_posted(review_id, reply_text)
        logger.info("Review %s approved and posted via HTTP API (location: %s)", review_id, location_name)

        return {
            "status": "ok",
            "message": "Draft approved and posted",
            "review_id": review_id,
            "location": location_name,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drafts/{review_id}/reject", dependencies=[Depends(verify_api_key)])
async def reject_draft(review_id: str, request: Request):
    """Reject a pending draft (owner did not approve it)."""
    if not review_id.strip():
        raise HTTPException(status_code=400, detail="review_id must not be empty")

    try:
        draft = get_pending_reply(review_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        if draft["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Can only reject pending drafts, this is {draft['status']}"
            )

        mark_rejected(review_id)
        logger.info("Review %s rejected via HTTP API", review_id)

        return {
            "status": "ok",
            "message": "Draft rejected",
            "review_id": review_id,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drafts/{review_id}/edit", dependencies=[Depends(verify_api_key)])
async def edit_draft(review_id: str, edit: EditRequest, request: Request):
    """Edit a pending draft and post the revised text to Google My Business."""
    if not review_id.strip():
        raise HTTPException(status_code=400, detail="review_id must not be empty")

    try:
        draft = get_pending_reply(review_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        if draft["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Can only edit pending drafts, this is {draft['status']}"
            )

        creds = request.app.state.creds
        location_name = draft["location_name"]

        result = post_reply(creds, location_name, review_id, edit.text)
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Failed to post reply to Google My Business"
            )

        mark_posted(review_id, edit.text)
        logger.info("Review %s edited and posted via HTTP API (location: %s)", review_id, location_name)

        return {
            "status": "ok",
            "message": "Draft edited and posted",
            "review_id": review_id,
            "location": location_name,
            "timestamp": datetime.now().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
