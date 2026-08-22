from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task
def trigger_ai_reply(conversation_id, message_id):
    """Trigger AI auto-reply for a webchat message."""
    from apps.inbox.models import Conversation, Message
    from apps.ai.services.ai_service import AIService

    conversation = Conversation.objects.filter(id=conversation_id).first()
    message = Message.objects.filter(id=message_id).first()
    if not conversation or not message:
        return

    if not conversation.ai_enabled:
        return

    ai_service = AIService(conversation.workspace)
    if ai_service.settings.mode in ("auto_reply", "hybrid"):
        ai_service.auto_reply(conversation, message)
