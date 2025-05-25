#!/usr/bin/env python3
"""Import clean data into new ChromaDB with resume capability."""
import sys
import os
import json
import time
sys.path.insert(0, 'src')

from mcp_memory_service.storage.chroma import ChromaMemoryStorage
from mcp_memory_service.config import CHROMA_PATH

print("ChromaDB Clean Import Tool (with Resume)")
print("=" * 50)

# Load the exported data
if not os.path.exists('chromadb_export.json'):
    print("Error: chromadb_export.json not found. Run extract_chromadb_data.py first.")
    sys.exit(1)

print("Loading exported data...")
with open('chromadb_export.json', 'r') as f:
    data = json.load(f)

print(f"Loaded {len(data['ids'])} documents")

# Initialize storage
print(f"\nConnecting to database at: {CHROMA_PATH}")
storage = ChromaMemoryStorage(CHROMA_PATH)

# Check current count
current_count = storage.collection.count()
print(f"Current database has {current_count} documents")

# Get existing IDs to avoid duplicates
print("Checking existing documents...")
existing_ids = set()
if current_count > 0:
    # Get all existing IDs
    result = storage.collection.get()
    existing_ids = set(result['ids'])
    print(f"Found {len(existing_ids)} existing documents")

# Import remaining documents
batch_size = 50  # Smaller batch size for reliability
imported_count = 0
skipped_count = 0
already_exists_count = len(existing_ids)
error_count = 0
start_time = time.time()

print(f"\nStarting import from document {len(existing_ids)}...")
print("Press Ctrl+C to stop (can be resumed later)")

try:
    for i in range(0, len(data['ids']), batch_size):
        batch_ids = data['ids'][i:i+batch_size]
        batch_documents = data['documents'][i:i+batch_size]
        batch_metadatas = data['metadatas'][i:i+batch_size]
        
        # Filter out already imported documents
        new_indices = []
        for j, doc_id in enumerate(batch_ids):
            if doc_id not in existing_ids:
                new_indices.append(j)
        
        if not new_indices:
            already_exists_count += len(batch_ids)
            continue
        
        # Prepare filtered batches
        filtered_ids = [batch_ids[j] for j in new_indices]
        filtered_documents = [batch_documents[j] for j in new_indices]
        filtered_metadatas = [batch_metadatas[j] for j in new_indices]
        
        # Process each document
        for j in range(len(filtered_ids)):
            try:
                doc_id = filtered_ids[j]
                document = filtered_documents[j]
                metadata = filtered_metadatas[j] or {}
                
                # Skip test documents
                if metadata.get('test', False):
                    skipped_count += 1
                    continue
                
                # Skip empty documents
                if not document or document.strip() == "":
                    skipped_count += 1
                    continue
                
                # Store directly using ChromaDB API
                storage.collection.add(
                    documents=[document],
                    metadatas=[metadata],
                    ids=[doc_id]
                )
                
                imported_count += 1
                existing_ids.add(doc_id)
                
            except Exception as e:
                error_count += 1
                if error_count <= 5:
                    print(f"\n  Error importing document: {str(e)}")
        
        # Progress update
        total_processed = already_exists_count + imported_count + skipped_count + error_count
        if total_processed % 1000 == 0:
            elapsed = time.time() - start_time
            rate = imported_count / elapsed if elapsed > 0 else 0
            remaining = len(data['ids']) - total_processed
            eta = remaining / rate if rate > 0 else 0
            print(f"\n  Progress: {total_processed}/{len(data['ids'])} documents")
            print(f"  Imported: {imported_count}, Rate: {rate:.1f} docs/sec")
            print(f"  ETA: {eta/60:.1f} minutes")

except KeyboardInterrupt:
    print("\n\nImport interrupted by user")
    print("The import can be resumed by running this script again")

print(f"\n\nImport summary:")
print(f"  Total documents in export: {len(data['ids'])}")
print(f"  Already existed: {already_exists_count}")
print(f"  Newly imported: {imported_count}")
print(f"  Skipped: {skipped_count}")
print(f"  Errors: {error_count}")
print(f"  Time taken: {(time.time() - start_time)/60:.1f} minutes")

# Verify
final_count = storage.collection.count()
print(f"\nFinal verification:")
print(f"  Documents in database: {final_count}")

if final_count < len(data['ids']) - skipped_count:
    print(f"\n⚠️  Not all documents were imported. Run this script again to continue.")
else:
    print(f"\n✅ All documents imported successfully!")
    # Clean up export file
    response = input("\nDelete export file? (y/n): ")
    if response.lower() == 'y':
        os.remove('chromadb_export.json')
        print("Export file deleted.")

print("\nDone!")