"""Job store for image packing jobs using Redis."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy initialization of Redis client
_redis_client = None


def get_redis_client():
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            import os
            
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis_client = redis.from_url(redis_url, decode_responses=True)
            logger.info("Redis client initialized for image packing job store")
        except ImportError:
            logger.error("redis package not installed. Install with: pip install redis")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            raise
    
    return _redis_client


def set_job_status(
    job_id: str,
    status: str,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    result: Optional[dict] = None,
    error: Optional[str] = None
):
    """Set job status in Redis."""
    try:
        client = get_redis_client()
        
        # Check if job already exists to preserve created_at
        key = f"image_packing:job:{job_id}"
        existing_data = client.get(key)
        existing_job = None
        if existing_data:
            try:
                existing_job = json.loads(existing_data)
            except (json.JSONDecodeError, TypeError):
                pass
        
        # Preserve created_at if job exists, otherwise create new timestamp
        created_at = existing_job.get("created_at") if existing_job else datetime.utcnow().isoformat()
        
        job_data = {
            "job_id": job_id,
            "status": status,
            "created_at": created_at,
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        if progress is not None:
            job_data["progress"] = progress
        if message is not None:
            job_data["message"] = message
        if result is not None:
            job_data["result"] = result
        if error is not None:
            job_data["error"] = error
        
        # Store with 24 hour expiration
        client.setex(
            key,
            timedelta(hours=24),
            json.dumps(job_data)
        )
        
        logger.debug(f"Updated job {job_id} status: {status}")
        
    except Exception as e:
        logger.error(f"Failed to set job status for {job_id}: {e}", exc_info=True)
        raise


def get_job_status(job_id: str) -> Optional[dict]:
    """Get job status from Redis."""
    try:
        client = get_redis_client()
        key = f"image_packing:job:{job_id}"
        data = client.get(key)
        
        if data is None:
            return None
        
        return json.loads(data)
        
    except Exception as e:
        logger.error(f"Failed to get job status for {job_id}: {e}", exc_info=True)
        return None


def delete_job(job_id: str):
    """Delete job from Redis."""
    try:
        client = get_redis_client()
        key = f"image_packing:job:{job_id}"
        client.delete(key)
        logger.debug(f"Deleted job {job_id} from Redis")
    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}", exc_info=True)
