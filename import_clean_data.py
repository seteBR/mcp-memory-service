#!/usr/bin/env python3
"""Import clean data into new ChromaDB."""
import sys
import os
import json
sys.path.insert(0, 'src')

from mcp_memory_service.storage.chroma import ChromaMemoryStorage
from mcp_memory_service.models.memory import Memory
from mcp_memory_service.config import CHROMA_PATH

print("ChromaDB Clean Import Tool")
print("=" * 50)

# Load the exported data
if not os.path.exists('chromadb_export.json'):
    print("Error: chromadb_export.json not found. Run extract_chromadb_data.py first.")
    sys.exit(1)

print("Loading exported data...")
with open('chromadb_export.json', 'r') as f:
    data = json.load(f)

print(f"Loaded {len(data['ids'])} documents")

# Initialize clean storage
print(f"\nInitializing clean database at: {CHROMA_PATH}")
storage = ChromaMemoryStorage(CHROMA_PATH)

# Import in batches
batch_size = 100
imported_count = 0
skipped_count = 0
error_count = 0

print("\nImporting documents...")
for i in range(0, len(data['ids']), batch_size):
    batch_ids = data['ids'][i:i+batch_size]
    batch_documents = data['documents'][i:i+batch_size]
    batch_metadatas = data['metadatas'][i:i+batch_size]
    
    # Process each document in the batch
    for j in range(len(batch_ids)):
        try:
            doc_id = batch_ids[j]
            document = batch_documents[j]
            metadata = batch_metadatas[j] or {}
            
            # Skip test documents
            if metadata.get('test', False):
                skipped_count += 1
                continue
            
            # Skip empty documents
            if not document or document.strip() == "":
                skipped_count += 1
                continue
            
            # Store directly using ChromaDB API to preserve IDs
            storage.collection.add(
                documents=[document],
                metadatas=[metadata],
                ids=[doc_id]
            )
            
            imported_count += 1
            
        except Exception as e:
            error_count += 1
            if error_count <= 5:
                print(f"  Error importing document {i+j}: {str(e)}")
    
    # Progress update
    if (i + batch_size) % 1000 == 0:
        print(f"  Processed {i + batch_size}/{len(data['ids'])} documents...")

print(f"\nImport complete!")
print(f"  Successfully imported: {imported_count} documents")
print(f"  Skipped: {skipped_count} documents")
print(f"  Errors: {error_count} documents")

# Verify
final_count = storage.collection.count()
print(f"\nVerification:")
print(f"  Documents in database: {final_count}")

# Clean up export file
if os.path.exists('chromadb_export.json'):
    os.remove('chromadb_export.json')
    print("\nCleaned up temporary export file")

print("\nDatabase restoration completed!")