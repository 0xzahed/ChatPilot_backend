"""Mock AI provider for development without real API keys.

Generates realistic responses based on simple pattern matching so the
entire UI and backend flow works before production credentials are configured.
"""

import re
from .base import BaseAIProvider, AIResponse, VisionResult


# Common complaint keywords (Bangla, English, Banglish)
COMPLAINT_KEYWORDS = [
    "complaint", "bad", "terrible", "worst", "late", "delay", "refund",
    "return", "broken", "damaged", "not received", "didn't receive",
    "haven't received", "poor service", "খারাপ", "দেরি", "ফেরত",
    "পাইনি", "এখনো পাইনি", "problem", "issue", "angry", "disappointed",
]

# Price question patterns
PRICE_PATTERNS = [
    r"price", r"cost", r"how much", r"দাম", r"কত", r"koto", r"price koto",
    r"kitnа", r"kitna", r"mol", r"মূল্য",
]

# Language detection patterns
LANG_PATTERNS = {
    "bn": [r"[\u0980-\u09FF]"],  # Bengali Unicode block
    "hi": [r"[\u0900-\u097F]"],  # Devanagari
    "ar": [r"[\u0600-\u06FF]"],  # Arabic
}

# Banglish patterns (romanized Bengali)
BANGLISH_WORDS = ["vai", "bhai", "kemon", "koto", "achen", "ki obostha",
                   "price koto", "dam koto", "apnar", "amar", "lagbe", "chai"]


class MockAIProvider(BaseAIProvider):
    name = "mock"

    def is_available(self) -> bool:
        return True

    def chat_completion(self, messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> AIResponse:
        # Extract the last user message
        user_msg = ""
        system_msg = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_msg = msg["content"]
                break
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
                break

        response_text = self._generate_response(user_msg, system_msg)
        return AIResponse(
            text=response_text,
            tokens_input=len(user_msg.split()) + 10,
            tokens_output=len(response_text.split()) + 10,
            model="mock-ai",
            confidence=0.85,
        )

    def vision_completion(self, image_url: str, prompt: str, temperature: float = 0.5) -> VisionResult:
        return VisionResult(
            description="I can see a product image. Based on the visual features, this appears to be a product from the catalog. "
                        "Let me check our inventory for matching items.",
            detected_products=[],
            confidence=0.6,
            metadata={"mock": True},
        )

    def _detect_language(self, text: str) -> str:
        for lang, patterns in LANG_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    return lang
        # Check for Banglish
        text_lower = text.lower()
        for word in BANGLISH_WORDS:
            if word in text_lower:
                return "banglish"
        return "en"

    def _is_complaint(self, text: str) -> bool:
        text_lower = text.lower()
        for keyword in COMPLAINT_KEYWORDS:
            if keyword.lower() in text_lower:
                return True
        return False

    def _is_price_question(self, text: str) -> bool:
        text_lower = text.lower()
        for pattern in PRICE_PATTERNS:
            if re.search(pattern, text_lower):
                return True
        return False

    def _generate_response(self, user_msg: str, system_msg: str) -> str:
        lang = self._detect_language(user_msg)
        is_complaint = self._is_complaint(user_msg)
        is_price = self._is_price_question(user_msg)

        if is_complaint:
            if lang in ("bn", "banglish"):
                return "আমি আপনার সমস্যাটি বুঝতে পেরেছি। আমি এই বিষয়ে একজন মানবিক প্রতিনিধির কাছে আপনার কথা পৌঁছে দিচ্ছি। দয়া করে একটু অপেক্ষা করুন, তারা শীঘ্রই আপনাকে সাহায্য করবে।"
            return "I understand your concern and I'm sorry for the inconvenience. I'm escalating this to a human agent who will assist you shortly. Please bear with us."

        if is_price:
            if lang == "bn":
                return "এই পণ্যটির দাম ৳১,৫০০। আপনি কোন সাইজ বা রঙ প্রয়োজন? অর্ডার করতে আমাকে আপনার নাম, ফোন নম্বর এবং ঠিকানা জানাতে পারেন।"
            if lang == "banglish":
                return "Vai, ei product tar dam ৳1,500. Apnar kon size ba color lagbe? Order korte amake apnar name, phone number ar address janate paren."
            return "This product is priced at ৳1,500. Which size or color would you prefer? To place an order, please share your name, phone number, and delivery address."

        # Greeting detection
        greeting_words = ["hi", "hello", "hey", "salam", "assalam", "নমস্কার", "হাই"]
        if any(word in user_msg.lower() for word in greeting_words):
            if lang == "bn":
                return "স্বাগতম! আমি আপনাকে কীভাবে সাহায্য করতে পারি? আমাদের পণ্য সম্পর্কে যেকোনো প্রশ্ন করতে পারেন।"
            return "Hello! How can I help you today? Feel free to ask about any of our products."

        # Order-related
        order_words = ["order", "buy", "purchase", "অর্ডার", "কিনতে", "চাই"]
        if any(word in user_msg.lower() for word in order_words):
            if lang == "bn":
                return "দুর্দান্ত! অর্ডার করার জন্য আমাকে আপনার সম্পূর্ণ নাম, ফোন নম্বর এবং ডেলিভারি ঠিকানা দিন।"
            return "Great! To place your order, please provide your full name, phone number, and delivery address."

        # Default
        if lang == "bn":
            return "আপনার বার্তাটি পেয়েছি। আমি আপনাকে সাহায্য করতে প্রস্তুত। আমাদের পণ্য সম্পর্কে যেকোনো প্রশ্ন করতে পারেন।"
        if lang == "banglish":
            return "Apnar message peyechi. Ami apnake help korte ready. Amader product somporke jekono question korte paren."
        return "Thank you for your message. I'm here to help. Feel free to ask about our products, prices, or place an order."
