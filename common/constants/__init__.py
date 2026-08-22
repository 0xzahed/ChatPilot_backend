from enum import Enum


class ChannelType(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    WEBSITE = "website"


class ConversationStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"


class MessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageSender(str, Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    AI = "ai"
    SYSTEM = "system"


class MessageStatus(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    PACKED = "packed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    REFUNDED = "refunded"


class PaymentStatus(str, Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    PARTIAL = "partial"
    REFUNDED = "refunded"


class ComplaintStatus(str, Enum):
    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ComplaintPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AIMode(str, Enum):
    OFF = "off"
    SUGGEST_ONLY = "suggest_only"
    AUTO_REPLY = "auto_reply"
    HYBRID = "hybrid"


class IntegrationType(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    WEBSITE = "website"
    SHOPIFY = "shopify"
    WOOCOMMERCE = "woocommerce"


class WorkspaceRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    AGENT = "agent"
    VIEWER = "viewer"
