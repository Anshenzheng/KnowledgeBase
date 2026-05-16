"""
Check import task status with details
"""
import requests
import json

task_id = "17e8f135-4de5-4195-ba6c-fe6f9e599265"

endpoint = f"http://localhost:8000/api/tasks/{task_id}"

print(f"Checking task: {task_id}\n")

response = requests.get(endpoint)
if response.status_code == 200:
    task = response.json()
    print(json.dumps(task, indent=2, ensure_ascii=False))
else:
    print(f"Error: {response.status_code}")
    print(response.text)
