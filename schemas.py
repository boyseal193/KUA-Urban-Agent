from pydantic import BaseModel
from typing import Optional


class PropertyInput(BaseModel):
    source: Optional[str] = "manual"
    listing_url: Optional[str] = None

    address: str
    city: Optional[str] = "Barcelona"
    neighbourhood: Optional[str] = None

    gba_m2: float
    asking_price: Optional[float] = None
    asking_rent_month: Optional[float] = None
    rent_per_m2: Optional[float] = 9

    ceiling_height: float
    loading_access: bool
    access_type: Optional[str] = None
    floor_level: Optional[str] = None
    building_type: Optional[str] = None
    current_use: Optional[str] = None

    description: Optional[str] = None

    price_per_m2_nra: Optional[float] = 15
    nra_efficiency: Optional[float] = 0.75