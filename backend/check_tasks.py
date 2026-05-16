"""
Check import task status
"""
import requests
import json

# Try different endpoint paths
endpoints = [
    "http://localhost:8000/api/knowledge/tasks",
    "http://localhost:8000/api/tasks",
    "http://localhost:8000/tasks"
]

for endpoint in endpoints:
    print(f"Trying: {endpoint}")
    response = requests.get(endpoint)
    if response.status_code == 200:
        print(f"[OK] Status Code: {response.status_code}")
        tasks = response.json()
        print(f"Found {len(tasks)} tasks\n")
        
        for task in tasks:
            print(f"Task ID: {task['id']}")
            print(f"  Name: {task['task_name']}")
            print(f"  Status: {task['status']}")
            print(f"  Progress: {task['progress_percentage']}%")
            print()
        break
    else:
        print(f"[ERROR] Status Code: {response.status_code}")
        print()
