"""
Verify imported knowledge
"""
import requests
import json

# Check knowledge sources
response = requests.get("http://localhost:8000/api/knowledge/sources")
if response.status_code == 200:
    sources = response.json()
    print(f"Found {len(sources)} knowledge sources\n")
    
    for source in sources[:5]:  # Show first 5
        print(f"Source ID: {source['id']}")
        print(f"  Title: {source['title']}")
        print(f"  Type: {source['source_type']}")
        print(f"  File: {source.get('file_name', 'N/A')}")
        print(f"  Created: {source['created_at']}")
        print()
else:
    print(f"Error: {response.status_code}")
