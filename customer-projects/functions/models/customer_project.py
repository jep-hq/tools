# pydantic model for customer project

from pydantic import BaseModel, ConfigDict, Field, BeforeValidator
from typing import Optional, Annotated
from bson import ObjectId
from datetime import datetime

PyObjectId = Annotated[str, BeforeValidator(str)]


class ProductModel(BaseModel):
    id: str
    name: str
    handle: str


class VariantModel(BaseModel):
    id: str
    name: str


class ChangeModel(BaseModel):
    token: str
    thumbnail_url: str
    variant = VariantModel
    created_at: datetime


class CustomerProjectModel(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    name: Optional[str]
    source: str
    customer_id: str
    product: ProductModel
    current: ChangeModel
    changes: list[ChangeModel]
    created_at: Optional[str]
    updated_at: Optional[str]
    deleted_at: Optional[str]
    is_deleted: bool
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class CustomerProjectCollection(BaseModel):
    projects: list[CustomerProjectModel]


class UpdateCustomerProjectModel(BaseModel):
    token: str
    thumbnail_url: Optional[str]
    variant = Optional[VariantModel]
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )
