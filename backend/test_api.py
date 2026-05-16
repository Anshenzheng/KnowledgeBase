"""
Quick test to verify API endpoints are working
"""
import requests
import json

# Test getting API endpoints
base_url = "http://localhost:8000"

print("=== Testing API Endpoints ===\n")

# Test 1: Check if server is running
try:
    response = requests.get(f"{base_url}/api/models/presets")
    print(f"[OK] Server is running on port 8000")
    print(f"  Models presets endpoint: {response.status_code}")
    if response.status_code == 200:
        print(f"  Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"[ERROR] Server error: {e}")

print("\n=== Test completed ===")
