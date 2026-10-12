from app.models.users import User, Role, Permission
from sqlalchemy.orm import Session
from app.models.vouchers import AuditLog
import datetime

class UserService:
    def __init__(self, db: Session):
        self.db = db

    def create_user(self, username, password_hash, full_name, roles_list=[]):
        user = User(username=username, password_hash=password_hash, full_name=full_name)
        self.db.add(user)
        self.db.flush()
        
        for role_name in roles_list:
            role = self.db.query(Role).filter(Role.name == role_name).first()
            if role:
                user.roles.append(role)
        
        self.db.commit()
        return user.id

    def check_permission(self, user_id, permission_code):
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user: return False
        
        # In a full implementation, we would link Role -> Permission
        # For now, we assume 'Admin' has all permissions
        for role in user.roles:
            if role.name == 'Admin':
                return True
        return False

    def log_action(self, user_id, action, table, record_id, old_val=None, new_val=None):
        log = AuditLog(
            user_id=user_id,
            action=action,
            table_name=table,
            record_id=record_id,
            old_value=str(old_val),
            new_value=str(new_val),
            timestamp=datetime.datetime.utcnow()
        )
        self.db.add(log)
        self.db.commit()
