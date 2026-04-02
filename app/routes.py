"""
FastAPI route handlers for the Google Reviews application.
"""

from datetime import datetime
from fastapi import APIRouter, Request, HTTPException

from app.services.database import (
    get_all_pending_replies, get_stats, get_pending_reply,
    mark_posted, mark_rejected
)
from app.services.polling import polling_loop
from app.services.google_api import post_reply

router = APIRouter()


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


@router.get("/stats")
async def stats():
    """Return database statistics."""
    db_stats = get_stats()
    return {
        "status": "ok",
        "database": db_stats,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/reviews")
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
async def telegram_webhook():
    """
    Telegram webhook endpoint.
    Currently unused (polling mode is active).
    """
    return {"status": "ok", "message": "Telegram webhook (polling mode active)"}


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


@router.post("/drafts/{review_id}/approve")
async def approve_draft(review_id: str, request: Request):
    """
    Approve a pending draft and post it to Google My Business.

    Phase 3: Draft approval workflow.
    """
    try:
        # Get the pending draft from database
        draft = get_pending_reply(review_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        if draft["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Can only approve pending drafts, this is {draft['status']}"
            )

        # Post the reply to Google My Business
        creds = request.app.state.creds
        location_name = draft["location_name"]
        reply_text = draft["draft_reply"]

        result = post_reply(creds, location_name, review_id, reply_text)
        if not result:
            raise HTTPException(
                status_code=500,
                detail="Failed to post reply to Google My Business"
            )

        # Mark as posted in database
        mark_posted(review_id, reply_text)

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


@router.post("/drafts/{review_id}/reject")
async def reject_draft(review_id: str, request: Request):
    """
    Reject a pending draft (owner did not approve it).

    Phase 3: Draft approval workflow.
    """
    try:
        # Get the pending draft from database
        draft = get_pending_reply(review_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")

        if draft["status"] != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Can only reject pending drafts, this is {draft['status']}"
            )

        # Mark as rejected in database
        mark_rejected(review_id)

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
