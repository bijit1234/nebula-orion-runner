import requests
import json

BASE_URL = "http://localhost:8000"

def test_flow():
    print("🚀 Testing NEBULA Flow...")
    
    # 1. Login
    print("\n[1] Logging in...")
    login = requests.post(
        f"{BASE_URL}/api/login",
        data={"username": "admin", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    if login.status_code != 200:
        print(f"❌ Login failed: {login.text}")
        return
    
    token = login.json()["access_token"]
    print(f"✅ Logged in! Token: {token[:30]}...")
    
    # 2. Create test file content
    print("\n[2] Creating test file...")
    test_content = """print("Hello from NEBULA!")
print("Python version:", __import__('sys').version)
print("Test successful! ✅")
"""
    
    # 3. Upload file
    print("\n[3] Uploading test file...")
    files = {"file": ("test.py", test_content, "text/plain")}
    upload = requests.post(
        f"{BASE_URL}/api/upload",
        files=files,
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if upload.status_code != 200:
        print(f"❌ Upload failed: {upload.text}")
        return
    print(f"✅ Uploaded: {upload.json()}")
    
    # 4. Run the file
    print("\n[4] Running file...")
    run = requests.post(
        f"{BASE_URL}/api/run/test.py",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if run.status_code != 200:
        print(f"❌ Run failed: {run.text}")
        return
    print(f"✅ Run started: {run.json()}")
    
    # 5. Get result
    print("\n[5] Getting result...")
    import time
    time.sleep(1)
    
    result = requests.get(
        f"{BASE_URL}/api/result/test.py",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"✅ Result: {result.json()}")

if __name__ == "__main__":
    test_flow()