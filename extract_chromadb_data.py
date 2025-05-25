#!/usr/bin/env python3
"""Extract data from ChromaDB using the API."""
import sys
import os
sys.path.insert(0, 'src')

import chromadb
from collections import Counter

# Use the corrupted database
SOURCE_DB = "/home/felipe/.local/share/mcp-memory/chroma_db_corrupted_20250524_224100"

print("ChromaDB Data Extraction")
print("=" * 50)

# We need to use a workaround to avoid the segfault
# First, let's try to connect directly
try:
    client = chromadb.PersistentClient(path=SOURCE_DB)
    print("Connected to ChromaDB")
    
    # Get the collection
    collection = client.get_collection("memory_collection")
    print(f"Found collection: memory_collection")
    
    # Get count
    count = collection.count()
    print(f"Collection has {count} documents")
    
    # Try to get a small batch of documents
    print("\nTrying to extract documents in small batches...")
    
    batch_size = 10
    offset = 0
    all_documents = []
    all_ids = []
    all_metadatas = []
    
    # Get all data at once (might work better than batching)
    try:
        print("Attempting to get all documents at once...")
        result = collection.get()
        
        if result and result.get('ids'):
            all_ids = result['ids']
            all_documents = result['documents']
            all_metadatas = result['metadatas']
            
            print(f"Successfully extracted {len(all_ids)} documents")
            
            # Check for duplicates
            id_counts = Counter(all_ids)
            duplicates = {id: count for id, count in id_counts.items() if count > 1}
            
            if duplicates:
                print(f"\nFound {len(duplicates)} duplicate IDs:")
                for id, count in list(duplicates.items())[:10]:
                    print(f"  {id}: {count} copies")
            else:
                print("\nNo duplicates found in the extracted data")
                
            # Save the data for migration
            import json
            
            export_data = {
                'ids': all_ids,
                'documents': all_documents,
                'metadatas': all_metadatas
            }
            
            with open('chromadb_export.json', 'w') as f:
                json.dump(export_data, f, indent=2)
                
            print(f"\nData exported to chromadb_export.json")
            print(f"Total documents: {len(all_ids)}")
            print(f"Unique documents: {len(set(all_ids))}")
            
    except Exception as e:
        print(f"Error extracting all documents: {str(e)}")
        print("This might be due to the database corruption")
    
except Exception as e:
    print(f"Error: {str(e)}")
    import traceback
    traceback.print_exc()