from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["admin", "staff", "viewer"]

OrderStatus = Literal[
    "draft",
    "confirmed",
    "packing",
    "shipped",
    "delivered",
    "cancelled",
]


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=500)


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    stock_quantity: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=5, ge=0)


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    stock_quantity: int | None = Field(default=None, ge=0)
    reorder_level: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class OrderItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class OrderCreate(BaseModel):
    customer_id: int = Field(gt=0)
    items: list[OrderItemCreate] = Field(min_length=1)
    tax_rate: Decimal = Field(default=Decimal("0.12"), ge=0, le=1)
    notes: str | None = Field(default=None, max_length=1000)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=8, max_length=200)
    role: UserRole
    is_active: bool = True


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=160)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: UserRole | None = None
    is_active: bool | None = None
