"""Utilities for database validation and health checks."""
from typing import Dict, Any, Tuple
import logging
import os
import json
import shutil
import signal
import multiprocessing
from datetime import datetime
from contextlib import contextmanager
import time

logger = logging.getLogger(__name__)

def validate_database(storage) -> Tuple[bool, str]:
    """Validate database health and configuration."""
    try:
        logger.debug("Starting database validation...")
        
        # Check if collection exists and is accessible
        logger.debug("Checking collection count...")
        try:
            collection_info = storage.collection.count()
            logger.debug(f"Collection count: {collection_info}")
            if collection_info == 0:
                logger.info("Database is empty but accessible")
        except Exception as e:
            logger.error(f"Error checking collection count: {str(e)}")
            return False, f"Cannot access collection: {str(e)}"
        
        # Verify embedding function is working
        logger.debug("Testing embedding function...")
        test_text = "Database validation test"
        try:
            # Test embedding generation without adding to database
            embedding = storage.embedding_function([test_text])
            logger.debug(f"Embedding generated: {len(embedding[0]) if embedding and len(embedding) > 0 else 0} dimensions")
            if not embedding or len(embedding) == 0 or len(embedding[0]) == 0:
                return False, "Embedding function is not working properly"
        except Exception as e:
            logger.error(f"Error testing embedding function: {str(e)}")
            return False, f"Embedding function error: {str(e)}"
        
        # Test database operations carefully
        logger.debug("Testing database operations...")
        test_id = f"validation_test_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        test_doc = "Database validation test document"
        test_metadata = {"test": True, "timestamp": datetime.now().isoformat()}
        
        # First check if there are any existing test documents to clean up
        try:
            logger.debug("Checking for stale test documents...")
            test_results = storage.collection.query(
                query_texts=[""],  # Empty query to get metadata matches
                n_results=100,
                where={"test": True}
            )
            if test_results.get('ids') and test_results['ids'][0]:
                stale_ids = test_results['ids'][0]
                logger.info(f"Found {len(stale_ids)} stale test documents, removing...")
                storage.collection.delete(ids=stale_ids)
                logger.info("Stale test documents removed")
        except Exception as e:
            logger.warning(f"Could not check for stale test documents: {str(e)}")
        
        # Now try the actual test with proper error handling
        operation_succeeded = False
        try:
            # Test add operation
            logger.debug(f"Testing add operation with ID: {test_id}")
            storage.collection.add(
                documents=[test_doc],
                metadatas=[test_metadata],
                ids=[test_id]
            )
            logger.debug("Add operation successful")
            
            # Brief pause to ensure data is persisted
            time.sleep(0.1)
            
            # Test query operation
            logger.debug("Testing query operation...")
            result = storage.collection.query(
                query_texts=[test_doc],
                n_results=1,
                where={"test": True}
            )
            
            if result.get('ids') and len(result['ids'][0]) > 0:
                logger.debug(f"Query operation successful, found {len(result['ids'][0])} results")
                operation_succeeded = True
            else:
                logger.warning("Query returned no results")
                
        except Exception as e:
            logger.error(f"Database operations test failed: {str(e)}")
            # Check if this is a segfault-related error
            error_str = str(e).lower()
            if 'segmentation' in error_str or 'core dump' in error_str:
                logger.error("Detected potential segmentation fault - database may be corrupted")
                return False, "Database corruption detected - segmentation fault"
        
        finally:
            # Always try to clean up test data
            try:
                logger.debug(f"Cleaning up test data with ID: {test_id}")
                storage.collection.delete(ids=[test_id])
                logger.debug("Cleanup successful")
            except Exception as cleanup_error:
                logger.warning(f"Failed to clean up test data: {str(cleanup_error)}")
                # If operations succeeded but cleanup failed, still consider it a pass
                if operation_succeeded:
                    logger.info("Operations succeeded despite cleanup failure")
        
        # Final validation result
        if operation_succeeded:
            return True, f"Database validation passed. Collection has {collection_info} documents"
        else:
            # If operations failed, database might have issues
            logger.error("Database operations failed - database may have corruption issues")
            return False, f"Database validation failed - operations test failed. Collection has {collection_info} documents"
            
    except Exception as e:
        logger.error(f"Database validation failed: {str(e)}")
        return False, f"Database validation failed: {str(e)}"

def get_database_stats(storage) -> Dict[str, Any]:
    """Get detailed database statistics."""
    try:
        count = storage.collection.count()
        
        # Get collection info
        collection_info = {
            "total_memories": count,
            "embedding_function": storage.embedding_function.__class__.__name__,
            "metadata": storage.collection.metadata
        }
        
        # Get storage info
        db_path = storage.path
        size = 0
        for root, dirs, files in os.walk(db_path):
            size += sum(os.path.getsize(os.path.join(root, name)) for name in files)
        
        storage_info = {
            "path": db_path,
            "size_bytes": size,
            "size_mb": round(size / (1024 * 1024), 2)
        }
        
        return {
            "collection": collection_info,
            "storage": storage_info,
            "status": "healthy"
        }
    except Exception as e:
        logger.error(f"Error getting database stats: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }

def backup_database(storage_path: str) -> str:
    """Create a backup of the database directory."""
    backup_path = f"{storage_path}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        shutil.copytree(storage_path, backup_path)
        logger.info(f"Database backed up to: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to backup database: {str(e)}")
        raise

def repair_database(storage) -> Tuple[bool, str]:
    """Attempt to repair database issues."""
    try:
        # First, try to validate current state
        is_valid, message = validate_database(storage)
        if is_valid and "segmentation" not in message.lower():
            return True, "Database is already healthy"
        
        logger.info("Attempting to repair database...")
        
        # Create backup first
        try:
            backup_path = backup_database(storage.path)
            logger.info(f"Created backup at: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to create backup: {str(e)}")
            # Continue anyway, but warn user
            logger.warning("Continuing repair without backup - data loss risk!")
        
        # Try to export existing data
        exported_data = None
        try:
            logger.info("Attempting to export existing data...")
            # Get data in smaller batches to avoid memory issues
            all_ids = []
            all_documents = []
            all_metadatas = []
            
            # First get all IDs
            result = storage.collection.get(limit=1)  # Get one to check structure
            if result and result.get('ids'):
                # Get total count
                total_count = storage.collection.count()
                logger.info(f"Found {total_count} documents to export")
                
                # Export in batches of 100
                batch_size = 100
                offset = 0
                
                while offset < total_count:
                    try:
                        batch = storage.collection.get(
                            limit=batch_size,
                            offset=offset
                        )
                        if batch and batch.get('ids'):
                            all_ids.extend(batch['ids'])
                            all_documents.extend(batch['documents'])
                            all_metadatas.extend(batch['metadatas'])
                            offset += batch_size
                            logger.debug(f"Exported {len(all_ids)}/{total_count} documents")
                        else:
                            break
                    except Exception as batch_error:
                        logger.error(f"Failed to export batch at offset {offset}: {str(batch_error)}")
                        break
                
                if all_ids:
                    exported_data = {
                        'ids': all_ids,
                        'documents': all_documents,
                        'metadatas': all_metadatas
                    }
                    logger.info(f"Successfully exported {len(all_ids)} documents")
                    
        except Exception as export_error:
            logger.error(f"Could not export existing data: {str(export_error)}")
            exported_data = None
        
        # Delete and recreate collection
        try:
            logger.info("Recreating collection...")
            collection_name = storage.collection.name
            
            # Delete the corrupted collection
            storage.client.delete_collection(collection_name)
            logger.info(f"Deleted collection: {collection_name}")
            
            # Recreate with same settings
            storage.collection = storage.client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=storage.embedding_function
            )
            logger.info(f"Recreated collection: {collection_name}")
            
        except Exception as recreate_error:
            logger.error(f"Failed to recreate collection: {str(recreate_error)}")
            return False, f"Failed to recreate collection: {str(recreate_error)}"
        
        # Restore data if we have it
        if exported_data and exported_data['ids']:
            logger.info(f"Restoring {len(exported_data['ids'])} documents...")
            restored_count = 0
            failed_count = 0
            
            # Restore in batches to avoid overwhelming the system
            batch_size = 50
            for i in range(0, len(exported_data['ids']), batch_size):
                batch_ids = exported_data['ids'][i:i+batch_size]
                batch_docs = exported_data['documents'][i:i+batch_size]
                batch_meta = exported_data['metadatas'][i:i+batch_size]
                
                try:
                    storage.collection.add(
                        documents=batch_docs,
                        metadatas=batch_meta,
                        ids=batch_ids
                    )
                    restored_count += len(batch_ids)
                    logger.debug(f"Restored {restored_count}/{len(exported_data['ids'])} documents")
                except Exception as restore_error:
                    logger.error(f"Failed to restore batch {i//batch_size}: {str(restore_error)}")
                    failed_count += len(batch_ids)
            
            logger.info(f"Restoration complete: {restored_count} succeeded, {failed_count} failed")
        
        # Validate repair
        is_valid, message = validate_database(storage)
        if is_valid:
            return True, f"Database successfully repaired. {message}"
        else:
            return False, f"Repair completed but validation failed: {message}"
            
    except Exception as e:
        logger.error(f"Error repairing database: {str(e)}")
        return False, f"Error repairing database: {str(e)}"