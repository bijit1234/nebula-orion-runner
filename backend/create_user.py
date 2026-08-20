import os
import sys
from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app.models import User, Base
from app.auth import get_password_hash

def create_user(username: str, password: str):
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Check if user exists
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"❌ User '{username}' already exists")
            return
        
        # Truncate password if needed (bcrypt limit is 72 bytes)
        if len(password) > 72:
            password = password[:72]
            print(f"⚠️ Password truncated to 72 characters")
        
        # Create user
        hashed = get_password_hash(password)
        user = User(
            username=username,
            hashed_password=hashed
        )
        db.add(user)
        db.commit()
        print(f"✅ User '{username}' created successfully!")
        
        # Verify
        user_check = db.query(User).filter(User.username == username).first()
        if user_check:
            print(f"✅ Verified: User '{username}' exists in database")
        else:
            print(f"❌ Verification failed: User not found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python create_user.py <username> <password>")
        print("Example: python create_user.py admin password123")
        sys.exit(1)
    
    create_user(sys.argv[1], sys.argv[2])