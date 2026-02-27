# Importing all models here ensures Alembic's autogenerate
# sees every table when it inspects Base.metadata.
from app.database import Base  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.campaign import Campaign  # noqa: F401
from app.models.character import Character  # noqa: F401
from app.models.share import CharacterShare  # noqa: F401
