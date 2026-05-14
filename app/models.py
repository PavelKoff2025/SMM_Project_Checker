from datetime import datetime, timedelta

from flask_login import UserMixin
from sqlalchemy import Index
from werkzeug.security import check_password_hash, generate_password_hash

from app import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_locked(self) -> bool:
        """Pure check — does not mutate state. Caller decides what to do."""
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    def record_failed_attempt(self) -> None:
        self.failed_attempts = (self.failed_attempts or 0) + 1
        if self.failed_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)

    def reset_failed_attempts(self) -> None:
        self.failed_attempts = 0
        self.locked_until = None


class ProjectCheck(db.Model):
    __tablename__ = 'checks'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    safe_filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    extracted_text = db.Column(db.Text)
    llm_response = db.Column(db.Text)
    final_report = db.Column(db.Text)
    grade = db.Column(db.String(20))
    llm_provider = db.Column(
        db.String(20), nullable=False, default='deepseek', server_default='deepseek'
    )
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False
    )

    user = db.relationship('User', backref=db.backref('checks', lazy=True))

    __table_args__ = (
        Index('ix_checks_user_created', 'user_id', 'created_at'),
    )


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))
