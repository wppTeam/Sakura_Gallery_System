"""
批量导入完整测试 (端到端)
测试通过 API 导入照片数据
"""
import asyncio
import httpx
import json
import os
from pathlib import Path


# API 配置
BASE_URL = "http://127.0.0.1:8002/api/v1"
EMAIL = "admin@buct.edu.cn"
PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "")


async def login() -> str:
    """登录获取 Token"""
    print("=" * 50)
    print("步骤 1: 登录获取 Token")
    print("=" * 50)
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/login",
            json={"email": EMAIL, "password": PASSWORD}
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            print(f"✅ 登录成功")
            print(f"   Token: {token[:20]}...")
            return token
        else:
            print(f"❌ 登录失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return None


async def validate_import_path(token: str, json_path: str):
    """验证导入路径"""
    print("\n" + "=" * 50)
    print("步骤 2: 验证导入路径")
    print("=" * 50)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/photos/import/validate",
            params={"json_path": json_path},
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 路径验证成功")
            print(f"   路径: {data.get('path')}")
            print(f"   类型: {'文件' if data.get('is_file') else '目录'}")
            print(f"   JSON 文件数: {data.get('json_files_count')}")
            
            json_files = data.get('json_files', [])
            if json_files:
                print(f"\n   找到的 JSON 文件:")
                for f in json_files[:5]:
                    print(f"     - {os.path.basename(f)}")
            
            return True
        else:
            print(f"❌ 路径验证失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return False


async def import_photos(token: str, json_path: str, image_folder: str = None):
    """执行批量导入"""
    print("\n" + "=" * 50)
    print("步骤 3: 执行批量导入")
    print("=" * 50)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "json_path": json_path
    }
    
    if image_folder:
        payload["image_folder"] = image_folder
    
    async with httpx.AsyncClient(timeout=300.0) as client:  # 5分钟超时
        print(f"\n正在导入...")
        print(f"  JSON 路径: {json_path}")
        if image_folder:
            print(f"  图片文件夹: {image_folder}")
        
        response = await client.post(
            f"{BASE_URL}/photos/import",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ 导入完成!")
            print(f"\n统计信息:")
            print(f"  总计: {data.get('total_count')} 张")
            print(f"  成功: {data.get('imported_count')} 张")
            print(f"  跳过: {data.get('skipped_count')} 张")
            print(f"  失败: {data.get('error_count')} 张")
            
            errors = data.get('errors', [])
            if errors:
                print(f"\n错误信息 (前 5 条):")
                for error in errors[:5]:
                    print(f"  ❌ {error}")
            
            print(f"\n消息: {data.get('message')}")
            return True
        else:
            print(f"❌ 导入失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return False


async def verify_imported_photos(token: str):
    """验证导入的照片"""
    print("\n" + "=" * 50)
    print("步骤 4: 验证导入的照片")
    print("=" * 50)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BASE_URL}/photos",
            params={"status": "pending", "limit": 10},
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            total = data.get('total', 0)
            items = data.get('items', [])
            
            print(f"✅ 查询成功")
            print(f"   待审核照片总数: {total}")
            
            if items:
                print(f"\n最近导入的照片 (前 5 张):")
                for photo in items[:5]:
                    print(f"\n  📷 {photo.get('filename')}")
                    print(f"     UUID: {photo.get('id')}")
                    print(f"     季节: {photo.get('season') or '未设置'}")
                    print(f"     分类: {photo.get('category') or '未设置'}")
                    print(f"     标签: {', '.join(photo.get('tags', [])) or '无'}")
                    print(f"     状态: {photo.get('status')}")
            
            return True
        else:
            print(f"❌ 查询失败: {response.status_code}")
            return False


async def create_test_json():
    """创建测试 JSON 文件"""
    print("=" * 50)
    print("准备测试数据")
    print("=" * 50)
    
    # 查找一个已存在的图片作为测试
    uploads_dir = Path(__file__).parent.parent / "uploads" / "originals"
    
    if not uploads_dir.exists():
        print("❌ 上传目录不存在")
        return None, None
    
    images = list(uploads_dir.glob("*.jpg")) + list(uploads_dir.glob("*.jpeg")) + list(uploads_dir.glob("*.png"))
    
    if not images:
        print("❌ 未找到测试图片")
        return None, None
    
    test_image = images[0]
    print(f"✅ 找到测试图片: {test_image.name}")
    
    # 创建测试 JSON
    test_data = [
        {
            "uuid": f"import-test-{os.urandom(4).hex()}",
            "filename": test_image.name,
            "original_path": str(test_image),
            "width": 1920,
            "height": 1080,
            "tags": {
                "attributes": {
                    "season": "Spring",
                    "category": "Landscape"
                },
                "keywords": ["测试导入", "批量处理", "校园风景"],
                "meta": {
                    "test": True,
                    "imported_at": "2024-01-01"
                }
            }
        }
    ]
    
    # 保存 JSON 文件
    test_json_path = Path(__file__).parent / "test_import_data.json"
    with open(test_json_path, 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 创建测试 JSON: {test_json_path}")
    
    return str(test_json_path), str(uploads_dir)


async def main():
    """主测试流程"""
    print("\n🚀 批量导入功能端到端测试\n")
    
    # 准备测试数据
    json_path, image_folder = await create_test_json()
    
    if not json_path:
        print("\n❌ 测试数据准备失败")
        return
    
    try:
        # 登录
        token = await login()
        if not token:
            return
        
        # 验证路径
        valid = await validate_import_path(token, json_path)
        if not valid:
            return
        
        # 执行导入
        success = await import_photos(token, json_path, image_folder)
        if not success:
            return
        
        # 验证导入结果
        await verify_imported_photos(token)
        
        print("\n" + "=" * 50)
        print("✅ 所有测试通过!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ 测试过程出错: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # 清理测试文件
        if json_path and os.path.exists(json_path):
            os.remove(json_path)
            print(f"\n🧹 清理测试文件: {json_path}")


if __name__ == "__main__":
    print("\n⚠️  注意: 请确保后端服务正在运行!")
    print("   启动命令: uvicorn app.main:app --reload --port 8002\n")
    
    asyncio.run(main())
