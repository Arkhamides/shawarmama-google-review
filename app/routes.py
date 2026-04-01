"""
Flask route handlers for the Google Reviews application.
"""

from datetime import datetime
from flask import jsonify

from app.services.database import (
    get_all_pending_replies, get_stats, get_pending_reply,
    mark_approved, mark_posted, mark_rejected
)
from app.services.polling import polling_loop
from app.services.google_api import post_reply


def register_routes(app, creds, locations):
    """Register all Flask routes with access to app context, creds, and locations."""

    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint for Cloud Run."""
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'authenticated': creds is not None,
            'locations_loaded': len(locations),
        }), 200

    @app.route('/stats', methods=['GET'])
    def stats():
        """Return database statistics."""
        db_stats = get_stats()
        return jsonify({
            'status': 'ok',
            'database': db_stats,
            'locations': len(locations),
            'timestamp': datetime.now().isoformat(),
        }), 200

    @app.route('/reviews', methods=['GET'])
    def get_all_reviews_endpoint():
        """Get all pending reviews waiting for owner approval."""
        pending = get_all_pending_replies('pending')
        return jsonify({
            'status': 'ok',
            'count': len(pending),
            'pending_reviews': pending,
            'timestamp': datetime.now().isoformat(),
        }), 200

    @app.route('/telegram', methods=['POST'])
    def telegram_webhook():
        """
        Telegram webhook endpoint.
        Phase 4 will implement this to handle:
        - Owner button clicks ([✅ Post] / [✏️ Edit])
        - Conversation flows for editing responses
        """
        # TODO: Phase 4 - integrate python-telegram-bot here
        return jsonify({'status': 'ok', 'message': 'Telegram webhook (Phase 4)'}), 200

    @app.route('/poll', methods=['POST'])
    def manual_poll():
        """Trigger polling immediately (for testing)."""
        try:
            polling_loop(creds, locations)
            return jsonify({'status': 'ok', 'message': 'Polling triggered'}), 200
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/drafts/<review_id>/approve', methods=['POST'])
    def approve_draft(review_id):
        """
        Approve a pending draft and post it to Google My Business.

        Phase 3: Draft approval workflow.
        """
        try:
            # Get the pending draft from database
            draft = get_pending_reply(review_id)
            if not draft:
                return jsonify({'status': 'error', 'message': 'Draft not found'}), 404

            if draft['status'] != 'pending':
                return jsonify({
                    'status': 'error',
                    'message': f"Can only approve pending drafts, this is {draft['status']}"
                }), 400

            # Post the reply to Google My Business
            location_name = draft['location_name']
            reply_text = draft['draft_reply']

            result = post_reply(creds, location_name, review_id, reply_text)
            if not result:
                return jsonify({
                    'status': 'error',
                    'message': 'Failed to post reply to Google My Business'
                }), 500

            # Mark as posted in database
            mark_posted(review_id, reply_text)

            return jsonify({
                'status': 'ok',
                'message': 'Draft approved and posted',
                'review_id': review_id,
                'location': location_name,
                'timestamp': datetime.now().isoformat(),
            }), 200

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500

    @app.route('/drafts/<review_id>/reject', methods=['POST'])
    def reject_draft(review_id):
        """
        Reject a pending draft (owner did not approve it).

        Phase 3: Draft approval workflow.
        """
        try:
            # Get the pending draft from database
            draft = get_pending_reply(review_id)
            if not draft:
                return jsonify({'status': 'error', 'message': 'Draft not found'}), 404

            if draft['status'] != 'pending':
                return jsonify({
                    'status': 'error',
                    'message': f"Can only reject pending drafts, this is {draft['status']}"
                }), 400

            # Mark as rejected in database
            mark_rejected(review_id)

            return jsonify({
                'status': 'ok',
                'message': 'Draft rejected',
                'review_id': review_id,
                'timestamp': datetime.now().isoformat(),
            }), 200

        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
