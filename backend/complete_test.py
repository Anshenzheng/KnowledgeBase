"""
Complete vector search test
"""
import requests
import json

print("=" * 70)
print(" " * 25 + "完整功能测试")
print("=" * 70)

# Test 1: Upload a file
print("\n[测试 1] 上传文件")
test_file = "test_files/test.txt"
try:
    with open(test_file, "rb") as f:
        files = {"file": ("test_vector.txt", f, "text/plain")}
        data = {"task_name": "向量搜索测试", "strategy": "add_new"}
        
        response = requests.post("http://localhost:8000/api/knowledge/upload/file", 
                                files=files, data=data)
        if response.status_code == 200:
            result = response.json()
            print(f"   上传成功！任务 ID: {result['task_id']}")
            task_id = result['task_id']
        else:
            print(f"   上传失败：{response.status_code}")
            exit(1)
except Exception as e:
    print(f"   错误：{e}")
    exit(1)

# Wait for processing
import time
print("\n[等待] 等待任务处理完成...")
time.sleep(3)

# Test 2: Check task status
print("\n[测试 2] 检查任务状态")
response = requests.get(f"http://localhost:8000/api/tasks/{task_id}")
if response.status_code == 200:
    task = response.json()
    print(f"   任务状态：{task['status']}")
    print(f"   进度：{task['progress_percentage']}%")
    if task['status'] == 'completed':
        print("   任务处理成功！")
    else:
        print("   任务尚未完成，请稍后重试")
        exit(1)
else:
    print(f"   查询失败：{response.status_code}")
    exit(1)

# Test 3: Vector search
print("\n[测试 3] 向量相似度搜索")
search_query = "test content"
response = requests.post(
    "http://localhost:8000/api/knowledge/search",
    json={"query": search_query, "top_k": 5}
)

if response.status_code == 200:
    results = response.json()
    print(f"   搜索成功！找到 {len(results)} 条结果")
    for i, result in enumerate(results[:3]):  # Show first 3 results
        print(f"\n   结果 {i+1}:")
        print(f"     来源：{result.get('source_title', 'N/A')}")
        content = result.get('content', 'N/A')
        if len(content) > 100:
            content = content[:100] + "..."
        print(f"     内容：{content}")
        print(f"     相似度：{result.get('score', 'N/A')}")
else:
    print(f"   搜索失败：{response.status_code}")
    print(f"   错误：{response.text}")

print("\n" + "=" * 70)
print(" " * 20 + "所有测试完成！")
print("=" * 70)
