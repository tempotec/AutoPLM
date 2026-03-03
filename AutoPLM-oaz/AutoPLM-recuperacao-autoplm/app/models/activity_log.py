from datetime import datetime
from app.extensions import db


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(100))
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50))
    target_id = db.Column(db.Integer)
    target_name = db.Column(db.String(255))
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    metadata_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', backref=db.backref('activity_logs', lazy='dynamic'))
    
    __table_args__ = (
        db.Index('idx_activity_user_created', 'user_id', 'created_at'),
        db.Index('idx_activity_action_created', 'action', 'created_at'),
    )
