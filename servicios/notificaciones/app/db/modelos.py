import datetime
import uuid

from sqlalchemy import DateTime, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ESQUEMA = "notificaciones"


class Base(DeclarativeBase):
    metadata = MetaData(schema=ESQUEMA)


class EventoProcesado(Base):
    __tablename__ = "evento_procesado"

    id_evento: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(50))
    procesado_en: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
