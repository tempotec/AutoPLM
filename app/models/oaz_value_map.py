from datetime import datetime
from app.extensions import db


class OazValueMap(db.Model):
    """De/Para: maps text values to OAZ WSIDs for 'Banco de Dados' fields."""
    __tablename__ = 'oaz_value_map'

    id = db.Column(db.Integer, primary_key=True)
    field_key = db.Column(db.String(50), nullable=False)   # e.g. "uno.10"
    text_value = db.Column(db.String(255), nullable=False)  # original text
    text_norm = db.Column(db.String(255), nullable=False)   # normalized (upper, no accents)
    wsid_value = db.Column(db.String(100), nullable=False)  # OAZ WSID
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('field_key', 'text_norm', name='uq_oaz_map_field_text'),
        db.Index('ix_oaz_map_field_key', 'field_key'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'field_key': self.field_key,
            'text_value': self.text_value,
            'wsid_value': self.wsid_value,
        }
