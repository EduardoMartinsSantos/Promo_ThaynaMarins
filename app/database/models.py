from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime,
    Text, ForeignKey, JSON, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(100), unique=True, nullable=False, index=True)
    source = Column(String(50), nullable=False, default="mercadolivre")  # extensível
    name = Column(String(500), nullable=False)
    category = Column(String(200))
    seller = Column(String(200))
    rating = Column(Numeric(3, 2))
    rating_count = Column(Integer, default=0)
    image_url = Column(Text)
    original_url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    promotions = relationship("Promotion", back_populates="product")


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    original_price = Column(Numeric(10, 2), nullable=False)
    promotional_price = Column(Numeric(10, 2), nullable=False)
    discount_percent = Column(Numeric(5, 2), nullable=False)
    savings_amount = Column(Numeric(10, 2), nullable=False)
    affiliate_url = Column(Text)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="promotions")
    coupons = relationship("Coupon", back_populates="promotion")
    sent_messages = relationship("SentMessage", back_populates="promotion")

    __table_args__ = (
        Index("idx_promotion_product_active", "product_id", "is_active"),
    )


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id"), nullable=False)
    code = Column(String(100), nullable=False)
    discount_type = Column(String(20))  # percent | fixed
    discount_value = Column(Numeric(10, 2))
    min_purchase = Column(Numeric(10, 2))
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    promotion = relationship("Promotion", back_populates="coupons")


class SentMessage(Base):
    __tablename__ = "sent_messages"

    id = Column(Integer, primary_key=True)
    promotion_id = Column(Integer, ForeignKey("promotions.id"), nullable=False)
    channel_id = Column(String(200), nullable=False)
    channel_type = Column(String(50))  # group | community | channel
    platform = Column(String(50), default="whatsapp")
    price_at_send = Column(Numeric(10, 2))
    affiliate_url = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="sent")  # sent | failed | deleted

    promotion = relationship("Promotion", back_populates="sent_messages")

    __table_args__ = (
        Index("idx_sent_promotion_channel", "promotion_id", "channel_id"),
    )


class Click(Base):
    __tablename__ = "clicks"

    id = Column(Integer, primary_key=True)
    sent_message_id = Column(Integer, ForeignKey("sent_messages.id"))
    product_external_id = Column(String(100), index=True)
    source = Column(String(50))
    clicked_at = Column(DateTime, default=datetime.utcnow)
    ip_hash = Column(String(64))


class Configuration(Base):
    __tablename__ = "configurations"

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(JSON, nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
