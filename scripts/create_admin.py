"""
Create initial admin user script
"""
import asyncio
import sys
import os
import secrets

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.core.database import AsyncSessionLocal, init_db
from app.crud.user import get_user_by_email, create_user
from app.schemas.user import UserCreate
# 导入所有模型以确保 Base.metadata 包含所有表定义
import app.models


async def create_admin():
    """Create initial admin user"""
    # 确保数据库表已创建
    print("Initializing database...")
    await init_db()
    
    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        sys.exit("请先设置 ADMIN_EMAIL 环境变量")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    generated = False
    if not admin_password:
        admin_password = secrets.token_urlsafe(18)
        generated = True
    admin_name = os.environ.get("ADMIN_NAME", "System Administrator")
    
    async with AsyncSessionLocal() as db:
        # Check if admin already exists
        existing_admin = await get_user_by_email(db, admin_email)
        if existing_admin:
            print(f"Admin user already exists: {admin_email}")
            return
        
        if generated:
            print("未提供 ADMIN_PASSWORD，已随机生成一次性口令：")
            print(admin_password)
            print("请立即登录并修改，此口令不会再次显示。")

        # Create admin user
        admin_user = UserCreate(
            email=admin_email,
            password=admin_password,
            full_name=admin_name
        )
        
        db_admin = await create_user(db, admin_user, role="admin")
        print(f"Admin user created successfully!")
        print(f"Email: {db_admin.email}")
        print(f"Password: {admin_password}")
        print(f"Role: {db_admin.role}")
        print("\nPlease change the default password after first login!")


if __name__ == "__main__":
    print("Creating initial admin user...")
    asyncio.run(create_admin())
