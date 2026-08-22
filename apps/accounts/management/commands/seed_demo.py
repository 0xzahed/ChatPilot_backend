"""Seed the database with realistic demo data.

Creates:
- Demo workspace with owner, admin, agent
- 25 customers across multiple channels
- 60 conversations with messages
- 30 products with categories
- 40 orders
- Labels, complaints, AI settings/instructions
- Plans and subscription
"""

import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import User
from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceSettings
from apps.customers.models import Customer, CustomerChannel, CustomerTimelineEvent
from apps.inbox.models import Conversation, Message, Label
from apps.products.models import Product, Category, ProductImage
from apps.orders.models import Order, OrderItem
from apps.complaints.models import Complaint
from apps.ai.models import AISettings, AIInstructions, AIEvent, AIUsage
from apps.integrations.models import Integration
from apps.billing.models import Plan, Subscription
from apps.notifications.models import Notification
from apps.webchat.models import WebchatConfig


CUSTOMER_NAMES = [
    "Rahim Ahmed", "Karim Hassan", "Fatima Begum", "Salma Akter", "Nasrin Jahan",
    "Imran Khan", "Tanvir Hossain", "Sadia Islam", "Mahin Rahman", "Nadia Sultana",
    "Arif Chowdhury", "Shamim Reza", "Rumana Afroz", "Sabbir Ahmed", "Tania Parvin",
    "Fahim Mahmud", "Jannatul Ferdous", "Rakibul Hasan", "Sumaiya Rahman", "Naimur Rahman",
    "Lamia Akhter", "Sakib Al Hasan", "Mitu Mondol", "Rifat Ahmed", "Priya Das",
]

PRODUCT_DATA = [
    ("Premium Cotton T-Shirt", "Clothing", 850, "COT-001", 45, "Premium quality cotton t-shirt, available in multiple colors and sizes."),
    ("Slim Fit Jeans", "Clothing", 1850, "JNS-002", 30, "Modern slim fit denim jeans with stretch fabric for comfort."),
    ("Running Sneakers", "Footwear", 3200, "SNK-003", 20, "Lightweight running sneakers with breathable mesh upper."),
    ("Leather Wallet", "Accessories", 1200, "WLT-004", 50, "Genuine leather bifold wallet with card slots."),
    ("Smart Watch Pro", "Electronics", 12500, "SMT-005", 15, "Feature-rich smartwatch with health tracking and notifications."),
    ("Wireless Earbuds", "Electronics", 2800, "EAR-006", 35, "Bluetooth 5.0 wireless earbuds with charging case."),
    ("Hoodie Premium", "Clothing", 1650, "HD-007", 25, "Comfortable fleece-lined hoodie with kangaroo pocket."),
    ("Sunglasses Classic", "Accessories", 950, "SUN-008", 40, "UV-protected polarized sunglasses with metal frame."),
    ("Backpack Travel", "Accessories", 2100, "BAG-009", 18, "Durable travel backpack with laptop compartment."),
    ("Cotton Saree", "Clothing", 3500, "SAR-010", 12, "Elegant handwoven cotton saree with traditional designs."),
    ("Formal Shirt", "Clothing", 1450, "SHT-011", 38, "Premium cotton formal shirt, slim fit, multiple colors."),
    ("Casual Sneakers", "Footwear", 2200, "SNK-012", 28, "Comfortable everyday casual sneakers with rubber sole."),
    ("Power Bank 20000mAh", "Electronics", 1800, "PWB-013", 42, "Fast charging power bank with dual USB ports."),
    ("Bluetooth Speaker", "Electronics", 2400, "SPK-014", 22, "Portable waterproof bluetooth speaker with deep bass."),
    ("Watch Leather Strap", "Accessories", 3200, "WCH-015", 16, "Analog wrist watch with genuine leather strap."),
    ("Denim Jacket", "Clothing", 2400, "JKT-016", 20, "Classic denim jacket with button front closure."),
    ("Cricket Bat", "Sports", 1800, "CRI-017", 14, "Premium willow cricket bat for professional play."),
    ("Yoga Mat", "Sports", 950, "YGA-018", 30, "Non-slip eco-friendly yoga mat with carrying strap."),
    ("Face Cream", "Beauty", 750, "FCR-019", 60, "Hydrating face cream for all skin types, 50ml."),
    ("Hair Oil Natural", "Beauty", 450, "HOI-020", 80, "Natural herbal hair oil for hair growth and strength."),
    ("Phone Case Premium", "Accessories", 350, "PHC-021", 100, "Shockproof phone case with slim design."),
    ("USB-C Cable", "Electronics", 250, "USBC-022", 200, "Fast charging USB-C to USB-C braided cable, 1m."),
    ("Kurti Embroidered", "Clothing", 1650, "KRT-023", 25, "Beautiful embroidered kurti with traditional patterns."),
    ("Sandals Leather", "Footwear", 1450, "SDL-024", 32, "Genuine leather sandals with cushioned sole."),
    ("Perfume Premium", "Beauty", 2200, "PRF-025", 18, "Long-lasting premium perfume, 100ml bottle."),
    ("Laptop Stand", "Accessories", 1200, "LPS-026", 28, "Adjustable aluminum laptop stand for ergonomic typing."),
    ("Water Bottle Steel", "Accessories", 550, "WTB-027", 120, "Insulated stainless steel water bottle, 750ml."),
    ("Cap Premium", "Accessories", 450, "CAP-028", 70, "Stylish cotton cap with adjustable strap."),
    ("Socks Pack of 3", "Clothing", 350, "SOC-029", 150, "Comfortable cotton socks, pack of 3 pairs."),
    ("Desk Lamp LED", "Electronics", 1400, "LMP-030", 24, "Adjustable LED desk lamp with USB charging port."),
]

CHANNELS = ["facebook", "instagram", "whatsapp", "website"]

SAMPLE_MESSAGES = [
    ("customer", "Hi, I want to know about your products"),
    ("ai", "Hello! Welcome to our store. We have a wide range of products. What are you looking for today?"),
    ("customer", "আমি একটি ভালো টি-শার্ট চাই"),
    ("ai", "আমাদের কাছে প্রিমিয়াম কটন টি-শার্ট আছে, দাম ৳৮৫০। আপনি কোন সাইজ এবং রঙ পছন্দ করেন?"),
    ("customer", "price koto?"),
    ("ai", "Vai, ei product tar dam ৳850. Apnar kon size lagbe? Order korte amake apnar name, phone number ar address janate paren."),
    ("customer", "XL size lagbe, navy blue color"),
    ("ai", "Great choice! XL size in navy blue is available. To place your order, please share your name, phone number, and delivery address."),
    ("customer", "My name is Rahim, phone 01712345678, address Mirpur, Dhaka"),
    ("ai", "Thank you Rahim! Your order for Premium Cotton T-Shirt (XL, Navy Blue) at ৳850 has been noted. Delivery charge is ৳60 inside Dhaka. Total: ৳910. Cash on delivery available. Shall I confirm the order?"),
    ("customer", "Yes, confirm it"),
    ("ai", "Your order has been confirmed! Order number: ORD-123456. You'll receive it within 2-3 business days. Thank you for shopping with us!"),
    ("customer", "এখনো পাইনি, অনেক দিন হয়ে গেছে"),
    ("ai", "আমি আপনার সমস্যাটি বুঝতে পেরেছি। আমি এই বিষয়ে একজন মানবিক প্রতিনিধির কাছে আপনার কথা পৌঁছে দিচ্ছি। দয়া করে একটু অপেক্ষা করুন।"),
    ("customer", "What products do you have?"),
    ("ai", "We have clothing, footwear, accessories, electronics, and more! Check our catalog for the full range. Is there something specific you're looking for?"),
    ("customer", "Do you have wireless earbuds?"),
    ("ai", "Yes! We have Wireless Earbuds (Bluetooth 5.0) with charging case for ৳2,800. Would you like to order?"),
    ("customer", "How long is the delivery time?"),
    ("ai", "Inside Dhaka: 1-2 business days. Outside Dhaka: 2-4 business days. Cash on delivery is available nationwide."),
]


class Command(BaseCommand):
    help = "Seed the database with realistic demo data"

    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")

        # ─── Users ───────────────────────────────────────────────
        owner, _ = User.objects.get_or_create(
            email="owner@demo.com",
            defaults={
                "username": "owner",
                "first_name": "Demo",
                "last_name": "Owner",
                "is_platform_admin": True,
                "email_verified_at": timezone.now(),
            },
        )
        owner.set_password("demo12345")
        owner.save()

        admin, _ = User.objects.get_or_create(
            email="admin@demo.com",
            defaults={"username": "admin", "first_name": "Demo", "last_name": "Admin"},
        )
        admin.set_password("demo12345")
        admin.save()

        agent, _ = User.objects.get_or_create(
            email="agent@demo.com",
            defaults={"username": "agent", "first_name": "Demo", "last_name": "Agent"},
        )
        agent.set_password("demo12345")
        agent.save()

        agent2, _ = User.objects.get_or_create(
            email="agent2@demo.com",
            defaults={"username": "agent2", "first_name": "Sarah", "last_name": "Agent"},
        )
        agent2.set_password("demo12345")
        agent2.save()

        # ─── Workspace ───────────────────────────────────────────
        workspace, _ = Workspace.objects.get_or_create(
            slug="demo-store",
            defaults={"name": "Demo Store", "owner": owner},
        )
        WorkspaceSettings.objects.get_or_create(workspace=workspace)
        WorkspaceMembership.objects.get_or_create(workspace=workspace, user=owner, defaults={"role": "owner"})
        WorkspaceMembership.objects.get_or_create(workspace=workspace, user=admin, defaults={"role": "admin"})
        WorkspaceMembership.objects.get_or_create(workspace=workspace, user=agent, defaults={"role": "agent"})
        WorkspaceMembership.objects.get_or_create(workspace=workspace, user=agent2, defaults={"role": "agent"})

        # ─── Plans & Subscription ────────────────────────────────
        trial_plan, _ = Plan.objects.get_or_create(
            name="Trial",
            defaults={"price_monthly": 4999, "message_limit": 6600, "team_member_limit": 3, "is_trial": True, "sort_order": 1},
        )
        standard_plan, _ = Plan.objects.get_or_create(
            name="Standard",
            defaults={"price_monthly": 12500, "message_limit": 18000, "team_member_limit": 5, "sort_order": 2,
                      "features": ["Facebook, Instagram & WhatsApp", "Comment Automation", "Webchat", "Image Understanding", "Omnichannel Inbox", "Multilingual Support", "Lead Management", "Order Management"]},
        )
        pro_plan, _ = Plan.objects.get_or_create(
            name="Pro",
            defaults={"price_monthly": 26000, "message_limit": 40000, "team_member_limit": 10, "sort_order": 3,
                      "features": ["Everything in Standard", "Priority Support", "Advanced Analytics", "Broadcast Messaging"]},
        )

        sub, _ = Subscription.objects.get_or_create(
            workspace=workspace,
            defaults={
                "plan": standard_plan,
                "status": "active",
                "current_period_start": timezone.now(),
                "current_period_end": timezone.now() + timedelta(days=30),
            },
        )

        # ─── Labels ──────────────────────────────────────────────
        labels_data = [
            ("New Customer", "blue"), ("Hot Lead", "red"), ("VIP", "purple"),
            ("Interested", "green"), ("Order Confirmed", "emerald"),
            ("Payment Pending", "yellow"), ("Complaint", "rose"),
            ("Follow Up", "orange"), ("Wholesale", "indigo"),
        ]
        labels = {}
        for name, color in labels_data:
            label, _ = Label.objects.get_or_create(workspace=workspace, name=name, defaults={"color": color})
            labels[name] = label

        # ─── Categories & Products ───────────────────────────────
        cat_names = set(p[1] for p in PRODUCT_DATA)
        categories = {}
        for cat_name in cat_names:
            cat, _ = Category.objects.get_or_create(workspace=workspace, name=cat_name)
            categories[cat_name] = cat

        products = []
        for name, cat_name, price, sku, stock, desc in PRODUCT_DATA:
            product, _ = Product.objects.get_or_create(
                workspace=workspace, sku=sku,
                defaults={
                    "name": name, "price": Decimal(str(price)),
                    "stock": stock, "category": categories[cat_name],
                    "description": desc, "is_available": stock > 0,
                    "brand": "Demo Brand",
                    "tags": [cat_name.lower()],
                },
            )
            products.append(product)

        # ─── Integrations ────────────────────────────────────────
        for itype in ["facebook", "instagram", "whatsapp", "website", "shopify", "woocommerce"]:
            Integration.objects.get_or_create(
                workspace=workspace, integration_type=itype,
                defaults={"status": "connected" if itype in ["facebook", "whatsapp", "website"] else "disconnected",
                          "is_active": itype in ["facebook", "whatsapp", "website"]},
            )

        # ─── AI Settings & Instructions ──────────────────────────
        ai_settings, _ = AISettings.objects.get_or_create(
            workspace=workspace,
            defaults={"mode": "hybrid", "provider": "mock", "model_name": "mock-ai"},
        )
        AIInstructions.objects.get_or_create(
            workspace=workspace,
            defaults={
                "business_name": "Demo Store",
                "business_description": "We are a multi-category retail store offering clothing, footwear, accessories, electronics, and more. We deliver nationwide with cash on delivery.",
                "tone": "Friendly, helpful, professional",
                "language": "en",
                "greeting": "Welcome to Demo Store! How can I help you today?",
                "delivery_policy": "Inside Dhaka: 1-2 days, ৳60. Outside Dhaka: 2-4 days, ৳120. Cash on delivery available.",
                "payment_policy": "Cash on delivery, bKash, Nagad, and bank transfer accepted.",
                "return_policy": "7-day return policy for unused items in original packaging.",
                "refund_policy": "Refunds processed within 7 business days after return inspection.",
                "cancellation_policy": "Orders can be cancelled before shipping.",
                "sales_strategy": "Always recommend products based on customer needs. Suggest complementary items. Collect order info efficiently.",
                "prohibited_responses": ["Never invent prices", "Never promise delivery dates we can't meet"],
                "faqs": [
                    {"question": "What are your delivery charges?", "answer": "Inside Dhaka ৳60, outside Dhaka ৳120."},
                    {"question": "Do you have cash on delivery?", "answer": "Yes, COD is available nationwide."},
                ],
            },
        )

        # ─── Webchat Config ──────────────────────────────────────
        WebchatConfig.objects.get_or_create(workspace=workspace)

        # ─── Customers ───────────────────────────────────────────
        customers = []
        for i, name in enumerate(CUSTOMER_NAMES):
            channel = CHANNELS[i % len(CHANNELS)]
            customer, created = Customer.objects.get_or_create(
                workspace=workspace, name=name,
                defaults={
                    "phone": f"017{random.randint(10000000, 99999999)}",
                    "email": f"customer{i+1}@example.com" if random.random() > 0.5 else "",
                    "is_vip": i < 5,
                    "language": random.choice(["en", "bn", "banglish"]),
                },
            )
            if created:
                CustomerChannel.objects.create(
                    customer=customer, channel=channel,
                    external_id=f"{channel}_user_{i+1}",
                    display_name=name,
                )
                # Add labels
                if i < 5:
                    customer.labels.add(labels["VIP"])
                elif i < 15:
                    customer.labels.add(labels["New Customer"])
                else:
                    customer.labels.add(labels["Interested"])
            customers.append(customer)

        # ─── Conversations & Messages ────────────────────────────
        agents = [agent, agent2]
        conversations = []
        for i in range(60):
            customer = customers[i % len(customers)]
            channel = CHANNELS[i % len(CHANNELS)]
            days_ago = random.randint(0, 25)
            created_at = timezone.now() - timedelta(days=days_ago, hours=random.randint(0, 23))

            handled_by = random.choice(["ai", "human", "mixed", "unassigned"])
            status = random.choice(["open", "open", "open", "closed"])
            assigned = random.choice(agents) if random.random() > 0.3 else None

            conv = Conversation.objects.create(
                workspace=workspace,
                customer=customer,
                channel=channel,
                status=status,
                handled_by=handled_by,
                assigned_to=assigned,
                created_at=created_at,
                last_message_at=created_at + timedelta(minutes=random.randint(1, 120)),
                unread_count=random.randint(0, 5) if status == "open" else 0,
                is_complaint=random.random() < 0.15,
                has_order=random.random() < 0.3,
                ai_enabled=random.random() > 0.1,
                language=customer.language,
            )

            # Add labels
            if conv.is_complaint:
                conv.labels.add(labels["Complaint"])
            if i % 7 == 0:
                conv.labels.add(labels["Hot Lead"])
            if i % 11 == 0:
                conv.labels.add(labels["Follow Up"])

            # Generate messages
            num_messages = random.randint(3, 12)
            msg_time = created_at
            for j in range(num_messages):
                sender, content = SAMPLE_MESSAGES[j % len(SAMPLE_MESSAGES)]
                msg_time += timedelta(minutes=random.randint(1, 30))

                Message.objects.create(
                    conversation=conv,
                    workspace=workspace,
                    sender_type=sender,
                    direction="inbound" if sender == "customer" else "outbound",
                    message_type="text",
                    content=content,
                    status="sent",
                    sent_by=assigned if sender == "agent" else None,
                    created_at=msg_time,
                )

            conv.last_message_preview = content[:100]
            conv.save(update_fields=["last_message_preview"])
            conversations.append(conv)

            # Timeline event
            CustomerTimelineEvent.objects.create(
                customer=customer,
                event_type="conversation_started",
                description=f"Started conversation via {channel}",
                created_at=created_at,
            )

        # ─── Orders ──────────────────────────────────────────────
        for i in range(40):
            customer = customers[i % len(customers)]
            product = random.choice(products)
            quantity = random.randint(1, 3)
            unit_price = product.price
            total_price = unit_price * quantity
            delivery_charge = Decimal("60")
            total = total_price + delivery_charge

            days_ago = random.randint(0, 25)
            created_at = timezone.now() - timedelta(days=days_ago)

            status = random.choice(["pending", "confirmed", "processing", "shipped", "delivered", "delivered", "delivered"])
            payment_status = "paid" if status == "delivered" else random.choice(["unpaid", "paid", "unpaid"])

            order = Order.objects.create(
                order_number=f"ORD-{100000 + i}",
                workspace=workspace,
                customer=customer,
                status=status,
                payment_status=payment_status,
                payment_method=random.choice(["cod", "bkash", "nagad"]),
                subtotal=total_price,
                delivery_charge=delivery_charge,
                total=total,
                shipping_address=f"House {random.randint(1, 200)}, Road {random.randint(1, 50)}, {random.choice(['Mirpur', 'Gulshan', 'Dhanmondi', 'Uttara', 'Banani'])}, Dhaka",
                phone=customer.phone,
                created_at=created_at,
            )
            OrderItem.objects.create(
                order=order, product=product,
                product_name=product.name, product_sku=product.sku,
                quantity=quantity, unit_price=unit_price, total_price=total_price,
            )

            if payment_status == "paid":
                customer.total_spent += total
                customer.total_orders += 1
                customer.save(update_fields=["total_spent", "total_orders"])
                CustomerTimelineEvent.objects.create(
                    customer=customer,
                    event_type="order_created",
                    description=f"Order {order.order_number} created for ৳{total}",
                    created_at=created_at,
                )

        # ─── Complaints ──────────────────────────────────────────
        for i in range(8):
            customer = customers[i]
            conv = customer.conversations.first()
            Complaint.objects.create(
                workspace=workspace,
                customer=customer,
                conversation=conv,
                title=f"Complaint from {customer.name}",
                description=random.choice([
                    "Product not received after 7 days",
                    "Received damaged product",
                    "Wrong product delivered",
                    "Poor delivery service",
                    "Want refund for returned item",
                ]),
                status=random.choice(["new", "assigned", "in_progress", "resolved", "closed"]),
                priority=random.choice(["medium", "high", "urgent"]),
                assigned_to=random.choice(agents) if random.random() > 0.3 else None,
                detected_by_ai=True,
            )

        # ─── AI Events & Usage ───────────────────────────────────
        for i in range(50):
            conv = random.choice(conversations)
            AIEvent.objects.create(
                workspace=workspace,
                conversation=conv,
                event_type=random.choice(["suggestion", "auto_reply", "language_detection", "complaint_detection"]),
                input_text="Customer message",
                output_text="AI response",
                detected_language=random.choice(["en", "bn", "banglish"]),
                is_complaint=random.random() < 0.15,
                confidence=random.uniform(0.7, 0.99),
                tokens_input=random.randint(50, 500),
                tokens_output=random.randint(20, 200),
                model_name="mock-ai",
                latency_ms=random.randint(100, 2000),
                created_at=timezone.now() - timedelta(days=random.randint(0, 25)),
            )

        # AI Usage per day for last 30 days
        for days_back in range(30):
            date = (timezone.now() - timedelta(days=days_back)).date()
            AIUsage.objects.get_or_create(
                workspace=workspace, date=date,
                defaults={
                    "ai_replies": random.randint(10, 50),
                    "ai_suggestions": random.randint(20, 80),
                    "comment_automation": random.randint(5, 30),
                    "vision_requests": random.randint(0, 10),
                    "tokens_input": random.randint(5000, 20000),
                    "tokens_output": random.randint(2000, 10000),
                },
            )

        # ─── Notifications ───────────────────────────────────────
        for i in range(10):
            Notification.objects.create(
                workspace=workspace,
                user=random.choice([owner, admin, agent, agent2]),
                notification_type=random.choice(["new_message", "conversation_assigned", "complaint", "order", "ai_escalation"]),
                title=random.choice([
                    "New message from customer",
                    "Conversation assigned to you",
                    "New complaint detected",
                    "New order received",
                    "AI escalation required",
                ]),
                body=f"Notification {i+1}",
                is_read=random.random() > 0.5,
                created_at=timezone.now() - timedelta(hours=random.randint(0, 72)),
            )

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully!"))
        self.stdout.write("  Owner:  owner@demo.com / demo12345")
        self.stdout.write("  Admin:  admin@demo.com / demo12345")
        self.stdout.write("  Agent:  agent@demo.com / demo12345")
