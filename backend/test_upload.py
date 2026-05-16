"""
Test script for PDF and Word file upload functionality
"""
import requests
import os

# Test file upload
upload_url = "http://localhost:8000/api/knowledge/upload/file"
files_url = "http://localhost:8000/api/knowledge/upload/files"

# Create test files
test_dir = "test_files"
os.makedirs(test_dir, exist_ok=True)

# Create test text file
with open(f"{test_dir}/test.txt", "w", encoding="utf-8") as f:
    f.write("这是一个测试文本文件。\n")
    f.write("This is a test text file for testing the upload functionality.\n")

# Create test markdown file
with open(f"{test_dir}/test.md", "w", encoding="utf-8") as f:
    f.write("# Test Markdown File\n\n")
    f.write("This is a **test** markdown file.\n")

print("Test files created in test_files/ directory")
print("\n=== Testing single file upload ===")

# Test single file upload
with open(f"{test_dir}/test.txt", "rb") as f:
    files = {"file": ("test.txt", f, "text/plain")}
    data = {"task_name": "Test Upload", "strategy": "skip"}
    
    response = requests.post(upload_url, files=files, data=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

print("\n=== Testing batch file upload ===")

# Test batch file upload
with open(f"{test_dir}/test.txt", "rb") as f1, open(f"{test_dir}/test.md", "rb") as f2:
    files = [
        ("files", ("test.txt", f1, "text/plain")),
        ("files", ("test.md", f2, "text/markdown"))
    ]
    data = {"task_name": "Batch Test Upload", "strategy": "skip"}
    
    response = requests.post(files_url, files=files, data=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.json()}")

print("\n=== Test completed ===")
print("You can check the import tasks at: http://localhost:8000/api/knowledge/tasks")
