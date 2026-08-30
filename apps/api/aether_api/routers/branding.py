from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_admin
from ..orm import User
from ..schemas import BrandingOut, BrandingPatch
from ..services.branding import get_branding, update_branding

router = APIRouter(prefix="/branding", tags=["branding"])


@router.get("", response_model=BrandingOut)
async def branding(db: AsyncSession = Depends(get_db)):
    return BrandingOut(**await get_branding(db))


@router.patch("", response_model=BrandingOut)
async def patch_branding(body: BrandingPatch, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    data = body.model_dump(exclude_unset=True)
    return BrandingOut(**await update_branding(db, data))
