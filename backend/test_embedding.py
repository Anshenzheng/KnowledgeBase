"""
Test script for embedding API
"""
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.text_embedding import TextEmbeddingService
from loguru import logger
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configure logger
logger.add(sys.stderr, level="INFO")

def test_embedding():
    """Test embedding generation"""
    api_key = os.getenv('ZHIPU_API_KEY')
    
    if not api_key:
        print("ERROR: ZHIPU_API_KEY not set!")
        print("\nPlease set your Zhipu API key:")
        print("1. Edit backend/.env file")
        print("2. Add: ZHIPU_API_KEY=your_api_key_here")
        print("3. Restart the backend service")
        print("\nGet your API key from: https://open.bigmodel.cn/")
        return False
    
    try:
        print("Testing Zhipu Embedding API...")
        service = TextEmbeddingService(model_name="embedding-2")
        
        test_text = "Hello, this is a test."
        print(f"Generating embedding for: '{test_text}'")
        
        embedding = service.generate_embedding(test_text)
        print(f"SUCCESS! Embedding dimension: {len(embedding)}")
        print(f"First 10 values: {embedding[:10]}")
        return True
        
    except Exception as e:
        print(f"FAILED: {e}")
        return False

if __name__ == "__main__":
    success = test_embedding()
    sys.exit(0 if success else 1)
