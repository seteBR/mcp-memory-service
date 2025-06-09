#!/usr/bin/env python3
"""
Script to rebuild the ChromaDB database from scratch.
This can fix corruption issues and segmentation faults.
"""
import os
import sys
import shutil
import chromadb
from datetime import datetime
import logging

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_memory_service.config import CHROMA_PATH, BACKUPS_PATH

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def backup_database():
    """Create a backup of the current database."""
    if not os.path.exists(CHROMA_PATH):
        logger.info("No database to backup")
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUPS_PATH, f"chroma_backup_{timestamp}")
    
    logger.info(f"Creating backup at: {backup_path}")
    shutil.copytree(CHROMA_PATH, backup_path)
    logger.info("Backup created successfully")
    
    return backup_path

def export_data():
    """Export all data from the current database."""
    logger.info("Attempting to export data from current database...")
    
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_collection("memory_collection")
        
        # Get all data
        logger.info("Fetching all documents...")
        data = collection.get(include=["metadatas", "documents"])
        
        if data['ids']:
            logger.info(f"Exported {len(data['ids'])} documents")
            return data
        else:
            logger.info("No data to export")
            return None
            
    except Exception as e:
        logger.error(f"Failed to export data: {str(e)}")
        return None

def rebuild_database(exported_data=None):
    """Rebuild the database from scratch."""
    logger.info("Rebuilding database...")
    
    # Remove old database
    if os.path.exists(CHROMA_PATH):
        logger.info(f"Removing old database at: {CHROMA_PATH}")
        shutil.rmtree(CHROMA_PATH)
    
    # Create new database
    logger.info("Creating new database...")
    os.makedirs(CHROMA_PATH, exist_ok=True)
    
    # Initialize new client
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    
    # Create collection with proper settings
    from chromadb.utils import embedding_functions
    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-mpnet-base-v2"
    )
    
    try:
        # Try to get existing collection first
        collection = client.get_collection("memory_collection")
        logger.warning("Collection already exists, deleting it...")
        client.delete_collection("memory_collection")
    except Exception:
        # Collection doesn't exist, that's fine
        pass
    
    collection = client.create_collection(
        name="memory_collection",
        embedding_function=embedding_function
    )
    
    logger.info("New database created successfully")
    
    # Reimport data if available
    if exported_data and exported_data['ids']:
        logger.info(f"Reimporting {len(exported_data['ids'])} documents...")
        
        # Import in batches to avoid issues
        batch_size = 100
        total = len(exported_data['ids'])
        
        for i in range(0, total, batch_size):
            end = min(i + batch_size, total)
            batch_ids = exported_data['ids'][i:end]
            batch_docs = exported_data['documents'][i:end]
            batch_meta = exported_data['metadatas'][i:end]
            
            try:
                collection.add(
                    ids=batch_ids,
                    documents=batch_docs,
                    metadatas=batch_meta
                )
                logger.info(f"Imported batch {i//batch_size + 1}/{(total + batch_size - 1)//batch_size}")
            except Exception as e:
                logger.error(f"Error importing batch: {str(e)}")
        
        logger.info("Data reimport completed")
    
    return True

def verify_new_database():
    """Verify the new database is working correctly."""
    logger.info("Verifying new database...")
    
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_collection("memory_collection")
        
        # Check count
        count = collection.count()
        logger.info(f"Collection has {count} documents")
        
        # Test operations
        test_id = f"verify_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        collection.add(
            ids=[test_id],
            documents=["Verification test"],
            metadatas=[{"test": True}]
        )
        
        # Query
        results = collection.query(
            query_texts=["Verification test"],
            n_results=1
        )
        
        # Cleanup
        collection.delete(ids=[test_id])
        
        logger.info("Database verification successful")
        return True
        
    except Exception as e:
        logger.error(f"Database verification failed: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("ChromaDB Database Rebuild Tool")
    logger.info("=" * 50)
    
    print("\nWARNING: This will rebuild your entire database.")
    print("A backup will be created, but the process may take time.")
    response = input("\nDo you want to continue? (yes/no): ")
    
    if response.lower() != 'yes':
        logger.info("Rebuild cancelled")
        sys.exit(0)
    
    # Step 1: Backup
    backup_path = backup_database()
    if backup_path:
        logger.info(f"Backup saved to: {backup_path}")
    
    # Step 2: Export data
    exported_data = export_data()
    
    # Step 3: Rebuild
    success = rebuild_database(exported_data)
    
    if success:
        # Step 4: Verify
        if verify_new_database():
            logger.info("\n✅ Database rebuild completed successfully!")
        else:
            logger.error("\n❌ Database rebuild completed but verification failed")
            logger.info(f"You can restore from backup at: {backup_path}")
    else:
        logger.error("\n❌ Database rebuild failed")
        if backup_path:
            logger.info(f"You can restore from backup at: {backup_path}")