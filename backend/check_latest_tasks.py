"""
Check latest import task status
"""
import requests
import json

response = requests.get("http://localhost:8000/api/tasks")
if response.status_code == 200:
    tasks = response.json()
    print(f"Found {len(tasks)} tasks\n")
    
    # Show the first 2 tasks (most recent)
    for task in tasks[:2]:
        print(f"Task ID: {task['id']}")
        print(f"  Name: {task['task_name']}")
        print(f"  Status: {task['status']}")
        print(f"  Progress: {task['progress_percentage']}%")
        print(f"  Items: {task['processed_items']}/{task['total_items']}")
        if task.get('error_message'):
            print(f"  Error: {task['error_message']}")
        print()
else:
    print(f"Error: {response.status_code}")
