"""
Test pgvector functionality
"""
import requests
import json

print("=" * 60)
print("测试 pgvector 功能")
print("=" * 60)

# Test 1: Check if vector table is created
print("\n1. 检查向量表创建状态...")
response = requests.get("http://localhost:8000/api/tasks")
if response.status_code == 200:
    tasks = response.json()
    print(f"   查询到 {len(tasks)} 个导入任务")
    
    # Find a completed task
    completed_tasks = [t for t in tasks if t['status'] == 'completed']
    if completed_tasks:
        print(f"   已完成任务：{len(completed_tasks)} 个")
        print(f"   最新任务：{completed_tasks[0]['task_name']}")
        print(f"   进度：{completed_tasks[0]['progress_percentage']}%")
else:
    print(f"   错误：{response.status_code}")

# Test 2: Try to upload a new file and check if embedding is stored
print("\n2. 测试新的文件上传...")
test_file = "test_files/test.txt"
try:
    with open(test_file, "rb") as f:
        files = {"file": ("test_pgvector.txt", f, "text/plain")}
        data = {"task_name": "pgvector 测试", "strategy": "skip"}
        
        response = requests.post("http://localhost:8000/api/knowledge/upload/file", 
                                files=files, data=data)
        if response.status_code == 200:
            result = response.json()
            print(f"   上传成功！")
            print(f"   任务 ID: {result['task_id']}")
            print(f"   状态：{result['status']}")
        else:
            print(f"   上传失败：{response.status_code}")
except Exception as e:
    print(f"   错误：{e}")

print("\n3. 等待任务处理完成...")
import time
time.sleep(3)

# Check task status
response = requests.get("http://localhost:8000/api/tasks")
if response.status_code == 200:
    tasks = response.json()
    if tasks:
        latest_task = tasks[0]
        print(f"   任务状态：{latest_task['status']}")
        print(f"   进度：{latest_task['progress_percentage']}%")
        print(f"   处理项目：{latest_task['processed_items']}/{latest_task['total_items']}")
        if latest_task.get('error_message'):
            print(f"   错误：{latest_task['error_message']}")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)
