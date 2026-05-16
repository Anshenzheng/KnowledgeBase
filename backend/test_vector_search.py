"""
Test vector similarity search
"""
import requests

print("=" * 60)
print("测试向量相似度搜索功能")
print("=" * 60)

# Test search
search_query = "test"
print(f"\n搜索查询: '{search_query}'")

response = requests.post(
    "http://localhost:8000/api/knowledge/search",
    json={"query": search_query, "top_k": 3}
)

if response.status_code == 200:
    results = response.json()
    print(f"搜索成功！找到 {len(results)} 条结果")
    for i, result in enumerate(results):
        print(f"\n--- 结果 {i+1} ---")
        print(f"来源: {result.get('source', 'N/A')}")
        print(f"内容: {result.get('content', 'N/A')[:100]}...")
        print(f"相似度: {result.get('score', 'N/A')}")
else:
    print(f"搜索失败: {response.status_code}")
    print(f"错误: {response.text}")

print("\n" + "=" * 60)
print("pgvector 向量搜索功能测试完成！")
print("=" * 60)
