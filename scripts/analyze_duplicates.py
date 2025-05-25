#!/usr/bin/env python3
"""
Script to analyze duplicate embeddings in ChromaDB without modifying anything.
"""
import os
import sys
import chromadb
from collections import defaultdict
import logging

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_memory_service.config import CHROMA_PATH

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_duplicates():
    """Analyze duplicate embeddings in ChromaDB."""
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
        
        total_docs = len(results['ids'])
        logger.info(f"Found {total_docs} total documents")
        
        # Group documents by content to find duplicates
        content_to_ids = defaultdict(list)
        id_to_metadata = {}
        
        for i, (doc_id, content, metadata) in enumerate(zip(results['ids'], results['documents'], results['metadatas'])):
            content_to_ids[content].append(doc_id)
            id_to_metadata[doc_id] = metadata
        
        # Analyze duplicates
        duplicate_groups = 0
        total_duplicates = 0
        
        print("\n=== Duplicate Analysis ===")
        for content, id_list in content_to_ids.items():
            if len(id_list) > 1:
                duplicate_groups += 1
                total_duplicates += len(id_list) - 1  # All but one are duplicates
                
                print(f"\nDuplicate Group {duplicate_groups}:")
                print(f"Content: {content[:100]}{'...' if len(content) > 100 else ''}")
                print(f"Number of duplicates: {len(id_list)}")
                
                # Show metadata for each duplicate
                for doc_id in id_list[:5]:  # Show max 5 examples
                    metadata = id_to_metadata[doc_id]
                    print(f"  - ID: {doc_id}")
                    print(f"    Tags: {metadata.get('tags', 'N/A')}")
                    print(f"    Timestamp: {metadata.get('timestamp', 'N/A')}")
                
                if len(id_list) > 5:
                    print(f"  ... and {len(id_list) - 5} more")
        
        print(f"\n=== Summary ===")
        print(f"Total documents: {total_docs}")
        print(f"Unique documents: {total_docs - total_duplicates}")
        print(f"Duplicate documents: {total_duplicates}")
        print(f"Duplicate groups: {duplicate_groups}")
        print(f"Space that could be saved: {(total_duplicates / total_docs * 100):.1f}%")
        
    except Exception as e:
        logger.error(f"Error during analysis: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    logger.info("Starting ChromaDB duplicate analysis...")
    analyze_duplicates()