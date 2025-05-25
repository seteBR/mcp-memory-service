#!/usr/bin/env python3
"""
Script to clean up duplicate embeddings in ChromaDB.
This issue can occur when multiple auto-sync instances run simultaneously.
"""
import os
import sys
import chromadb
from datetime import datetime
import logging
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_memory_service.config import CHROMA_PATH

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_duplicates():
    """Remove duplicate embeddings from ChromaDB."""
    chroma_path = CHROMA_PATH
    logger.info(f"Connecting to ChromaDB at: {chroma_path}")
    
    # Initialize ChromaDB client
    client = chromadb.PersistentClient(path=chroma_path)
    
    try:
        # Get the collection
        collection = client.get_collection("memory_collection")
        logger.info(f"Connected to collection: memory_collection")
        
        # Get all documents
        logger.info("Fetching all documents...")
        results = collection.get(include=["metadatas", "documents"])
        
        if not results['ids']:
            logger.info("No documents found in collection")
            return
        
        logger.info(f"Found {len(results['ids'])} total documents")
        
        # Group documents by content to find duplicates
        content_to_ids = defaultdict(list)
        for i, (doc_id, content) in enumerate(zip(results['ids'], results['documents'])):
            content_to_ids[content].append((doc_id, i))
        
        # Find and remove duplicates
        duplicates_removed = 0
        for content, id_list in content_to_ids.items():
            if len(id_list) > 1:
                logger.info(f"Found {len(id_list)} duplicates for content: {content[:100]}...")
                
                # Sort by metadata timestamp if available, keep the oldest
                sorted_ids = []
                for doc_id, idx in id_list:
                    metadata = results['metadatas'][idx]
                    timestamp = metadata.get('timestamp', '1970-01-01T00:00:00')
                    sorted_ids.append((timestamp, doc_id))
                
                sorted_ids.sort()  # Keep the oldest
                
                # Remove all but the first (oldest)
                ids_to_remove = [doc_id for _, doc_id in sorted_ids[1:]]
                
                logger.info(f"Removing {len(ids_to_remove)} duplicate IDs")
                collection.delete(ids=ids_to_remove)
                duplicates_removed += len(ids_to_remove)
        
        logger.info(f"Cleanup complete. Removed {duplicates_removed} duplicate documents")
        
        # Verify final count
        final_count = collection.count()
        logger.info(f"Final document count: {final_count}")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        return False
    
    return True

def verify_collection_health():
    """Verify the collection is healthy after cleanup."""
    chroma_path = CHROMA_PATH
    client = chromadb.PersistentClient(path=chroma_path)
    
    try:
        collection = client.get_collection("memory_collection")
        
        # Test basic operations
        test_id = f"health_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        test_doc = "Health check test document"
        
        # Add
        collection.add(
            documents=[test_doc],
            metadatas=[{"test": True}],
            ids=[test_id]
        )
        
        # Query
        results = collection.query(
            query_texts=[test_doc],
            n_results=1
        )
        
        # Delete
        collection.delete(ids=[test_id])
        
        logger.info("Collection health check passed")
        return True
        
    except Exception as e:
        logger.error(f"Collection health check failed: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("Starting ChromaDB duplicate cleanup...")
    
    # Backup reminder
    logger.warning("IMPORTANT: This will modify your database. Make sure you have a backup!")
    response = input("Do you want to continue? (yes/no): ")
    
    if response.lower() != 'yes':
        logger.info("Cleanup cancelled")
        sys.exit(0)
    
    # Run cleanup
    success = cleanup_duplicates()
    
    if success:
        logger.info("Verifying collection health...")
        if verify_collection_health():
            logger.info("Database cleanup successful and verified!")
        else:
            logger.error("Database cleanup completed but verification failed")
    else:
        logger.error("Database cleanup failed")
        sys.exit(1)