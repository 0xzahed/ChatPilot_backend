"""Core AI service that orchestrates provider calls, context building,
language detection, complaint detection, product matching, and human handoff."""

import time
import logging
from django.db.models import Q
from django.utils import timezone

from apps.ai.providers.factory import get_provider
from apps.ai.providers.base import AIResponse
from apps.ai.models import AISettings, AIInstructions, AIEvent, AIUsage
from apps.inbox.models import Conversation, Message
from apps.products.models import Product
from apps.complaints.models import Complaint

logger = logging.getLogger(__name__)


class AIService:
    """Per-workspace AI service."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.settings = self._get_settings()
        self.instructions = self._get_instructions()
        self.provider = self._get_provider()

    def _get_settings(self):
        settings_obj, _ = AISettings.objects.get_or_create(workspace=self.workspace)
        return settings_obj

    def _get_instructions(self):
        instructions, _ = AIInstructions.objects.get_or_create(workspace=self.workspace)
        return instructions

    def _get_provider(self):
        return get_provider(
            provider_name=self.settings.provider,
            api_key=self._decrypt_api_key(),
            model=self.settings.model_name,
            base_url=self.settings.base_url,
        )

    def _decrypt_api_key(self):
        from common.utils import decrypt_value
        if self.settings.api_key_encrypted:
            return decrypt_value(self.settings.api_key_encrypted)
        return ""

    def _build_system_prompt(self) -> str:
        """Build the system prompt from business instructions."""
        inst = self.instructions
        parts = []
        if inst.business_name:
            parts.append(f"You are the AI sales and support assistant for {inst.business_name}.")
        if inst.business_description:
            parts.append(f"Business description: {inst.business_description}")
        if inst.tone:
            parts.append(f"Tone: {inst.tone}")
        if inst.greeting:
            parts.append(f"Greeting: {inst.greeting}")
        if inst.delivery_policy:
            parts.append(f"Delivery policy: {inst.delivery_policy}")
        if inst.payment_policy:
            parts.append(f"Payment policy: {inst.payment_policy}")
        if inst.return_policy:
            parts.append(f"Return policy: {inst.return_policy}")
        if inst.refund_policy:
            parts.append(f"Refund policy: {inst.refund_policy}")
        if inst.cancellation_policy:
            parts.append(f"Cancellation policy: {inst.cancellation_policy}")
        if inst.sales_strategy:
            parts.append(f"Sales strategy: {inst.sales_strategy}")
        if inst.prohibited_responses:
            parts.append(f"Never do: {', '.join(inst.prohibited_responses)}")
        if inst.escalation_rules:
            parts.append(f"Escalation rules: {', '.join(str(r) for r in inst.escalation_rules)}")
        if inst.faqs:
            for faq in inst.faqs:
                if isinstance(faq, dict):
                    parts.append(f"Q: {faq.get('question', '')}\nA: {faq.get('answer', '')}")
        if inst.custom_instructions:
            parts.append(inst.custom_instructions)

        parts.append("IMPORTANT RULES:")
        parts.append("- Always respond in the language the customer uses (Bangla, English, or Banglish).")
        parts.append("- Never invent product prices. If you don't know a price, ask the customer for the product name.")
        parts.append("- If the customer is complaining, express empathy and escalate to a human agent.")
        parts.append("- To collect an order, ask for: name, phone number, delivery address, and quantity.")
        parts.append("- Be concise, friendly, and helpful.")

        return "\n\n".join(parts)

    def _build_context_messages(self, conversation: Conversation, max_messages: int = 20) -> list:
        """Build the message context for the AI, respecting context window."""
        recent_messages = conversation.messages.order_by("-created_at")[:max_messages]
        msgs = list(reversed(recent_messages))

        context = [{"role": "system", "content": self._build_system_prompt()}]

        # Add customer info
        customer = conversation.customer
        customer_info = f"Customer: {customer.name}, Phone: {customer.phone}, Language: {conversation.language}"
        if customer.total_orders > 0:
            customer_info += f", Previous orders: {customer.total_orders}, Total spent: ৳{customer.total_spent}"
        context.append({"role": "system", "content": customer_info})

        # Add relevant products if available
        products = self.workspace.products.filter(is_available=True)[:10]
        if products:
            product_list = "\n".join([
                f"- {p.name}: ৳{p.discount_price or p.price} (SKU: {p.sku}, Stock: {p.stock})"
                for p in products
            ])
            context.append({"role": "system", "content": f"Available products:\n{product_list}"})

        # Add conversation messages
        for msg in msgs:
            if msg.message_type == "note":
                continue
            if msg.sender_type == "customer":
                context.append({"role": "user", "content": msg.content})
            elif msg.sender_type in ("ai", "agent"):
                context.append({"role": "assistant", "content": msg.content})

        return context

    def generate_suggestion(self, conversation: Conversation) -> dict:
        """Generate an AI suggested reply for a conversation."""
        if self.settings.mode == "off":
            return {"suggestion": "", "enabled": False}

        start_time = time.time()
        context = self._build_context_messages(conversation)

        response = self.provider.chat_completion(
            messages=context,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
        )

        latency_ms = int((time.time() - start_time) * 1000)

        # Detect language and complaint
        last_customer_msg = ""
        for msg in conversation.messages.order_by("-created_at"):
            if msg.sender_type == "customer":
                last_customer_msg = msg.content
                break

        detected_language = self._detect_language(last_customer_msg)
        is_complaint = self._detect_complaint(last_customer_msg)

        # Update conversation language
        if detected_language and detected_language != conversation.language:
            conversation.language = detected_language
            conversation.save(update_fields=["language"])

        # Log AI event
        self._log_ai_event(
            conversation=conversation,
            event_type="suggestion",
            input_text=last_customer_msg,
            output_text=response.text,
            detected_language=detected_language,
            is_complaint=is_complaint,
            confidence=response.confidence,
            tokens_input=response.tokens_input,
            tokens_output=response.tokens_output,
            model_name=response.model,
            latency_ms=latency_ms,
        )

        # Update usage
        self._update_usage("ai_suggestions")

        # Check for human handoff
        needs_handoff = self._check_handoff(conversation, is_complaint, response.confidence)

        return {
            "suggestion": response.text,
            "enabled": True,
            "language": detected_language,
            "is_complaint": is_complaint,
            "confidence": response.confidence,
            "needs_handoff": needs_handoff,
            "tokens_input": response.tokens_input,
            "tokens_output": response.tokens_output,
        }

    def auto_reply(self, conversation: Conversation, customer_message: Message) -> dict:
        """Generate and send an AI auto-reply."""
        if self.settings.mode not in ("auto_reply", "hybrid"):
            return {"sent": False, "reason": "Auto-reply is not enabled."}

        result = self.generate_suggestion(conversation)

        if result.get("needs_handoff") and self.settings.enable_human_handoff:
            # Create system message about handoff
            Message.objects.create(
                conversation=conversation,
                workspace=self.workspace,
                sender_type="system",
                direction="outbound",
                message_type="system",
                content="Conversation escalated to a human agent.",
                status="sent",
            )
            conversation.handled_by = "human"
            conversation.ai_enabled = False
            conversation.save(update_fields=["handled_by", "ai_enabled"])

            # Create complaint if detected
            if result.get("is_complaint"):
                self._create_complaint(conversation)

            from apps.inbox.consumers import broadcast_new_message
            broadcast_new_message(conversation.messages.last())
            return {"sent": False, "reason": "Escalated to human agent."}

        # Send the AI reply
        ai_message = Message.objects.create(
            conversation=conversation,
            workspace=self.workspace,
            sender_type="ai",
            direction="outbound",
            message_type="text",
            content=result["suggestion"],
            status="sent",
            ai_metadata={
                "confidence": result.get("confidence"),
                "language": result.get("language"),
                "tokens_input": result.get("tokens_input"),
                "tokens_output": result.get("tokens_output"),
            },
        )

        # Update conversation
        conversation.last_message_at = timezone.now()
        conversation.last_message_preview = result["suggestion"][:100]
        conversation.handled_by = "ai"
        conversation.save(update_fields=["last_message_at", "last_message_preview", "handled_by"])

        # Update usage
        self._update_usage("ai_replies")

        # Broadcast
        from apps.inbox.consumers import broadcast_new_message
        broadcast_new_message(ai_message)

        return {"sent": True, "message_id": str(ai_message.id), "suggestion": result["suggestion"]}

    def recognize_product_image(self, conversation: Conversation, image_url: str) -> dict:
        """Analyze a customer-sent image and match products from catalog."""
        if not self.settings.enable_vision:
            return {"enabled": False}

        prompt = "Analyze this product image. Describe what you see and identify the type of product, color, and any visible features."

        result = self.provider.vision_completion(image_url, prompt)

        # Search catalog for matching products
        description_lower = result.description.lower()
        products = self.workspace.products.filter(is_available=True)
        matched = []
        for product in products:
            score = 0
            for word in product.name.lower().split():
                if word in description_lower:
                    score += 1
            if product.brand and product.brand.lower() in description_lower:
                score += 2
            if score > 0:
                matched.append({"product_id": str(product.id), "name": product.name,
                                "price": str(product.discount_price or product.price),
                                "score": score, "confidence": min(score / 5, 1.0)})

        matched.sort(key=lambda x: x["score"], reverse=True)

        self._log_ai_event(
            conversation=conversation,
            event_type="product_recognition",
            input_text=image_url,
            output_text=result.description,
            confidence=result.confidence,
        )
        self._update_usage("vision_requests")

        return {
            "description": result.description,
            "matched_products": matched[:5],
            "confidence": result.confidence,
        }

    def _detect_language(self, text: str) -> str:
        """Detect the language of a text."""
        if not self.settings.enable_language_detection:
            return "en"
        # Use mock provider's detection
        from apps.ai.providers.mock_provider import MockAIProvider
        mock = MockAIProvider()
        return mock._detect_language(text)

    def _detect_complaint(self, text: str) -> bool:
        """Detect if a message is a complaint."""
        if not self.settings.enable_complaint_detection:
            return False
        from apps.ai.providers.mock_provider import MockAIProvider
        mock = MockAIProvider()
        return mock._is_complaint(text)

    def _check_handoff(self, conversation: Conversation, is_complaint: bool, confidence: float) -> bool:
        """Determine if human handoff is needed."""
        if is_complaint and self.settings.enable_human_handoff:
            return True
        if confidence < self.settings.confidence_threshold:
            return True
        # Check for explicit human request
        last_msgs = conversation.messages.filter(sender_type="customer").order_by("-created_at")[:3]
        human_keywords = ["human", "agent", "manager", "মানুষ", "এজেন্ট", "support"]
        for msg in last_msgs:
            if any(kw in msg.content.lower() for kw in human_keywords):
                return True
        return False

    def _create_complaint(self, conversation: Conversation):
        """Create a complaint record from a conversation."""
        complaint, created = Complaint.objects.get_or_create(
            conversation=conversation,
            defaults={
                "workspace": self.workspace,
                "customer": conversation.customer,
                "title": f"Complaint from {conversation.customer.name}",
                "description": conversation.last_message_preview,
                "priority": "high",
                "detected_by_ai": True,
            },
        )
        if created:
            conversation.is_complaint = True
            conversation.save(update_fields=["is_complaint"])

    def _log_ai_event(self, conversation, event_type, input_text="", output_text="",
                      detected_language="", is_complaint=None, confidence=None,
                      tokens_input=0, tokens_output=0, model_name="", latency_ms=0):
        """Log an AI event for audit and analytics."""
        AIEvent.objects.create(
            workspace=self.workspace,
            conversation=conversation,
            event_type=event_type,
            input_text=input_text[:2000],
            output_text=output_text[:2000],
            detected_language=detected_language,
            is_complaint=is_complaint,
            confidence=confidence,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            model_name=model_name,
            latency_ms=latency_ms,
        )

    def _update_usage(self, field: str):
        """Update daily AI usage record."""
        today = timezone.now().date()
        usage, _ = AIUsage.objects.get_or_create(
            workspace=self.workspace, date=today,
        )
        if field == "ai_replies":
            usage.ai_replies += 1
        elif field == "ai_suggestions":
            usage.ai_suggestions += 1
        elif field == "comment_automation":
            usage.comment_automation += 1
        elif field == "vision_requests":
            usage.vision_requests += 1
        usage.save()
