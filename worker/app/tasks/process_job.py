"""Job processing task."""

import asyncio
import json
import logging
from typing import Optional

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.tasks.process_job.process_job")
def process_job(self, job_id: int) -> dict:
    """
    Process a job: parse PDF, resolve SKUs, and prepare for layout.
    
    Pipeline:
    1. Parse PDF with Docling (Feature 6)
    2. Resolve SKUs (Feature 7)
    3. Check for needs_input state
    4. Continue to layout if all resolved
    
    Args:
        job_id: Job ID to process
        
    Returns:
        Dict with status and details
    """
    logger.info(f"Starting job processing for job_id={job_id}")
    
    try:
        # Import here to avoid circular imports
        import sys
        import importlib.util
        from datetime import datetime
        from sqlalchemy.orm import Session
        
        # Import worker services using relative imports
        from ..services.pdf_parser import PDFParserService, PDFParserError
        from ..services.sku_resolver import SKUResolverService
        from ..services.sizing_service import SizingService
        from ..services.packing_service import PackingService
        from ..services.render_service import RenderService
        
        # Save reference to worker's app module and temporarily remove it
        worker_app = sys.modules.get('app')
        if worker_app:
            del sys.modules['app']
        
        # Add /api_code to path FIRST
        sys.path.insert(0, '/api_code')
        
        # Now import API modules (will get /api_code/app/...)
        import app.database as api_db_module
        SessionLocal = api_db_module.SessionLocal
        
        import app.models.job as api_job_module
        Job = api_job_module.Job
        
        import app.models.job_item as api_job_item_module
        JobItem = api_job_item_module.JobItem
        
        import app.storage.factory as api_storage_module
        get_storage_driver = api_storage_module.get_storage_driver
        
        # Remove /api_code from path
        sys.path.remove('/api_code')
        
        # Restore worker's app module
        if worker_app:
            sys.modules['app'] = worker_app
        
        db: Session = SessionLocal()
        
        try:
            # Get job
            job = db.query(Job).filter(Job.id == job_id).first()
            if not job:
                logger.error(f"Job {job_id} not found")
                return {"status": "error", "message": f"Job {job_id} not found"}
            
            # Update status to processing
            job.status = "processing"
            job.updated_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Job {job_id} status updated to 'processing'")
            
            # ===== Feature 6: Parse PDF with Docling =====
            try:
                # Get storage driver
                storage_driver = get_storage_driver(db, job.tenant_id)
                
                # Download PDF from storage
                logger.info(f"Downloading PDF from {job.picklist_uri}")
                pdf_content = asyncio.run(storage_driver.download_file(job.picklist_uri))
                
                # Get valid SKUs from asset catalog for validation
                try:
                    from ..models import Asset
                    valid_skus = set(
                        asset.sku_normalized 
                        for asset in db.query(Asset).filter(Asset.tenant_id == job.tenant_id).all()
                    )
                    logger.info(f"Loaded {len(valid_skus)} valid SKUs from catalog for validation")
                except Exception as e:
                    logger.warning(f"Failed to load SKU catalog: {e}")
                    valid_skus = None
                
                # Parse PDF with RobustPDFParser (primary) or Docling (fallback)
                parser = PDFParserService(valid_skus=valid_skus)
                parsed_items = asyncio.run(parser.parse_pdf(pdf_content, job.picklist_uri))
                
                logger.info(f"Parsed {len(parsed_items)} items from PDF")
                
                # Save raw extraction to manifest_json
                manifest_data = {
                    "raw_extraction": [
                        {
                            "sku": item.sku,
                            "quantity": item.quantity,
                            "size_label": item.size_label
                        }
                        for item in parsed_items
                    ],
                    "parsed_at": datetime.utcnow().isoformat(),
                    "item_count": len(parsed_items)
                }
                job.manifest_json = json.dumps(manifest_data)
                db.commit()
                
                # Create job_items
                for parsed_item in parsed_items:
                    job_item = JobItem(
                        job_id=job.id,
                        sku=parsed_item.sku,
                        quantity=parsed_item.quantity,
                        size_label=parsed_item.size_label,
                        picklist_position=parsed_item.position,  # ✅ Preservar ordem do picklist
                        status="pending"  # Will be updated in Feature 7
                    )
                    db.add(job_item)
                
                db.commit()
                logger.info(f"Created {len(parsed_items)} job items")
                
            except PDFParserError as e:
                logger.error(f"PDF parsing failed: {str(e)}")
                job.status = "failed"
                job.manifest_json = json.dumps({"error": str(e), "stage": "parsing"})
                job.updated_at = datetime.utcnow()
                db.commit()
                return {"status": "error", "message": f"PDF parsing failed: {str(e)}"}
            
            # ===== Feature 7: Resolve SKUs =====
            resolver = SKUResolverService()
            
            # Refresh job to get items
            db.refresh(job)
            
            pending_items_data = {}
            has_pending_items = False
            resolved_count = 0
            missing_count = 0
            ambiguous_count = 0
            
            for item in job.items:
                logger.info(f"Resolving SKU: {item.sku} (item_id={item.id})")
                
                resolution = asyncio.run(resolver.resolve_sku(item.sku, job.tenant_id, db))
                
                if resolution.status == "resolved":
                    # Update item with resolved asset
                    item.asset_id = resolution.asset_id
                    item.status = "resolved"
                    resolved_count += 1
                    logger.info(
                        f"SKU resolved: {item.sku} -> asset_id={resolution.asset_id} "
                        f"(score={resolution.score:.3f})"
                    )
                    
                elif resolution.status == "missing":
                    # No match found
                    item.status = "missing"
                    missing_count += 1
                    has_pending_items = True
                    pending_items_data[str(item.id)] = {
                        "status": "missing",
                        "candidates": []
                    }
                    logger.warning(f"SKU not found: {item.sku}")
                    
                elif resolution.status == "ambiguous":
                    # Multiple similar matches
                    item.status = "ambiguous"
                    ambiguous_count += 1
                    has_pending_items = True
                    pending_items_data[str(item.id)] = {
                        "status": "ambiguous",
                        "candidates": [
                            {
                                "asset_id": c.asset_id,
                                "sku": c.sku,
                                "file_uri": c.file_uri,
                                "score": c.score
                            }
                            for c in resolution.candidates
                        ]
                    }
                    logger.warning(
                        f"SKU ambiguous: {item.sku} ({len(resolution.candidates)} candidates)"
                    )
            
            # Update manifest with resolution results and pending items data
            manifest = json.loads(job.manifest_json) if job.manifest_json else {}
            manifest.update({
                "resolution": {
                    "resolved": resolved_count,
                    "missing": missing_count,
                    "ambiguous": ambiguous_count,
                    "resolved_at": datetime.utcnow().isoformat()
                },
                "pending_items_data": pending_items_data
            })
            job.manifest_json = json.dumps(manifest)
            
            # Update job status based on resolution results
            if has_pending_items:
                job.status = "needs_input"
                job.updated_at = datetime.utcnow()
                db.commit()
                logger.info(
                    f"Job {job_id} needs input: {missing_count} missing, "
                    f"{ambiguous_count} ambiguous"
                )
            else:
                # All items resolved, continue to Phase 4: Sizing, Packing, Rendering
                logger.info(f"Job {job_id} fully resolved: {resolved_count} items. Starting Phase 4...")
                db.commit()
                
                # ===== Feature 8: Apply Sizing =====
                try:
                    # Import additional models
                    import app.models.asset as api_asset_module
                    Asset = api_asset_module.Asset
                    
                    import app.models.machine as api_machine_module
                    Machine = api_machine_module.Machine
                    
                    import app.models.sizing_profile as api_sizing_profile_module
                    SizingProfile = api_sizing_profile_module.SizingProfile
                    
                    # Get machine and sizing profile
                    machine = db.query(Machine).filter(Machine.id == job.machine_id).first()
                    if not machine:
                        logger.error(f"Machine {job.machine_id} not found for job {job_id}")
                        job.status = "failed"
                        manifest["error"] = "Machine not found"
                        job.manifest_json = json.dumps(manifest)
                        db.commit()
                        return {"status": "error", "message": "Machine not found"}
                    
                    # Get all sizing profiles for tenant (for auto-matching)
                    all_profiles = db.query(SizingProfile).filter(
                        SizingProfile.tenant_id == job.tenant_id
                    ).all()
                    
                    # Build prefix map for fast lookup
                    prefix_map = {}
                    default_profile = None
                    
                    for profile in all_profiles:
                        if profile.sku_prefix:
                            # Normalize prefix (remove dashes for matching)
                            normalized_prefix = profile.sku_prefix.lower().replace("-", "")
                            prefix_map[normalized_prefix] = profile
                        if profile.is_default:
                            default_profile = profile
                    
                    # Fallback to job's sizing_profile_id if no default found
                    if not default_profile and job.sizing_profile_id:
                        default_profile = db.query(SizingProfile).filter(
                            SizingProfile.id == job.sizing_profile_id
                        ).first()
                    
                    logger.info(
                        f"Loaded {len(all_profiles)} sizing profiles: "
                        f"{len(prefix_map)} with prefixes, "
                        f"default: {default_profile.size_label if default_profile else 'None'}"
                    )
                    
                    sizing_service = SizingService()
                    sizing_warnings = []
                    invalid_items = []
                    scaled_items = 0
                    sizing_matches = {}  # Track which profile matched each SKU
                    
                    # Refresh job to get updated items
                    db.refresh(job)
                    
                    # Get all resolved items
                    resolved_items = [item for item in job.items if item.status == "resolved"]
                    
                    for item in resolved_items:
                        # Get asset
                        asset = db.query(Asset).filter(Asset.id == item.asset_id).first()
                        if not asset:
                            logger.error(f"Asset {item.asset_id} not found for item {item.id}")
                            invalid_items.append(item.id)
                            item.status = "invalid"
                            continue
                        
                        # Auto-match sizing profile by SKU prefix
                        sizing_profile = None
                        matched_by = "none"
                        
                        # Normalize SKU for matching (already normalized in DB)
                        sku_normalized = item.sku.lower().replace("-", "")
                        
                        # Try to match by prefix (longest first for specificity)
                        sorted_prefixes = sorted(prefix_map.keys(), key=len, reverse=True)
                        for prefix in sorted_prefixes:
                            if sku_normalized.startswith(prefix):
                                sizing_profile = prefix_map[prefix]
                                matched_by = f"prefix:{prefix_map[prefix].sku_prefix}"
                                break
                        
                        # Fallback to size_label if set
                        if not sizing_profile and item.size_label:
                            sizing_profile = db.query(SizingProfile).filter(
                                SizingProfile.tenant_id == job.tenant_id,
                                SizingProfile.size_label == item.size_label
                            ).first()
                            if sizing_profile:
                                matched_by = "size_label"
                        
                        # Use default if no specific profile found
                        if not sizing_profile:
                            sizing_profile = default_profile
                            matched_by = "default" if default_profile else "none"
                        
                        # Track match
                        sizing_matches[item.sku] = {
                            "profile_id": sizing_profile.id if sizing_profile else None,
                            "profile_label": sizing_profile.size_label if sizing_profile else None,
                            "target_width_mm": sizing_profile.target_width_mm if sizing_profile else None,
                            "matched_by": matched_by
                        }
                        
                        # Log match for debugging
                        if sizing_profile:
                            logger.debug(
                                f"SKU '{item.sku}' → Profile '{sizing_profile.size_label}' "
                                f"({sizing_profile.target_width_mm}mm) via {matched_by}"
                            )
                        else:
                            logger.warning(f"No sizing profile found for SKU '{item.sku}'")
                        
                        # Apply sizing
                        sizing_result = asyncio.run(sizing_service.apply_sizing(
                            item, asset, sizing_profile, machine
                        ))
                        
                        if not sizing_result.is_valid:
                            logger.error(
                                f"Invalid item {item.id}: {sizing_result.error_message}"
                            )
                            invalid_items.append(item.id)
                            item.status = "invalid"
                            sizing_warnings.append(
                                f"Item {item.id} (SKU: {item.sku}): {sizing_result.error_message}"
                            )
                            continue
                        
                        # Update item with final dimensions
                        item.final_width_mm = sizing_result.final_width_mm
                        item.final_height_mm = sizing_result.final_height_mm
                        
                        if sizing_result.scale_applied < 1.0:
                            scaled_items += 1
                        
                        sizing_warnings.extend(sizing_result.warnings)
                        
                        logger.info(
                            f"Item {item.id} sized: {item.final_width_mm:.1f}x{item.final_height_mm:.1f}mm"
                        )
                    
                    db.commit()
                    
                    # Update manifest with sizing results
                    manifest["sizing"] = {
                        "total_items": len(resolved_items),
                        "valid_items": len(resolved_items) - len(invalid_items),
                        "invalid_items": len(invalid_items),
                        "scaled_items": scaled_items,
                        "warnings": sizing_warnings,
                        "profile_matches": sizing_matches  # Show which profile matched each SKU
                    }
                    job.manifest_json = json.dumps(manifest)
                    db.commit()
                    
                    # Log sizing summary
                    logger.info(
                        f"Sizing complete: {len(resolved_items) - len(invalid_items)}/{len(resolved_items)} valid, "
                        f"{scaled_items} scaled, {len(sizing_warnings)} warnings"
                    )
                    
                    # If we have invalid items, mark job as failed
                    if invalid_items:
                        job.status = "failed"
                        job.updated_at = datetime.utcnow()
                        db.commit()
                        logger.error(f"Job {job_id} has {len(invalid_items)} invalid items")
                        return {
                            "status": "error",
                            "message": f"Job has {len(invalid_items)} invalid items",
                            "invalid_items": invalid_items
                        }
                    
                    logger.info(f"Sizing completed: {len(resolved_items)} items processed")
                    
                    # ===== Feature 9: Pack Items =====
                    packing_service = PackingService()
                    
                    # Get items that need packing (all valid sized items)
                    items_to_pack_raw = [
                        item for item in job.items
                        if item.status == "resolved" and item.final_width_mm and item.final_height_mm
                    ]
                    
                    # ✅ Ordenar baseado no mode
                    if job.mode == "sequence":
                        # Mode sequence: manter ordem EXATA do picklist original
                        items_to_pack = sorted(
                            items_to_pack_raw,
                            key=lambda x: x.picklist_position if x.picklist_position is not None else 999999
                        )
                        logger.info(
                            f"Packing {len(items_to_pack)} items in SEQUENCE mode (by picklist_position). "
                            f"Order: {[item.sku for item in items_to_pack[:5]]}... "
                            f"(first 5 SKUs)"
                        )
                    else:
                        # Mode optimize: ordem será definida pelo PackingService
                        items_to_pack = items_to_pack_raw
                        logger.info(
                            f"Packing {len(items_to_pack)} items in OPTIMIZE mode (will be reordered by area). "
                            f"Starting order: {[item.sku for item in items_to_pack[:5]]}..."
                        )
                    
                    if not items_to_pack:
                        logger.error(f"No items to pack for job {job_id}")
                        job.status = "failed"
                        manifest["error"] = "No items to pack"
                        job.manifest_json = json.dumps(manifest)
                        db.commit()
                        return {"status": "error", "message": "No items to pack"}
                    
                    # Pack items
                    packing_result = asyncio.run(packing_service.pack_items(
                        items=items_to_pack,
                        machine=machine,
                        mode=job.mode or "sequence"
                    ))
                    
                    # Update items with placement positions
                    for base in packing_result.bases:
                        for placement in base.placements:
                            item = db.query(JobItem).filter(JobItem.id == placement.item_id).first()
                            if item:
                                item.base_index = base.index
                                item.x_mm = placement.x_mm
                                item.y_mm = placement.y_mm
                                item.status = "packed"
                    
                    db.commit()
                    
                    # Update manifest with packing results
                    manifest["packing"] = packing_result.to_dict()
                    job.manifest_json = json.dumps(manifest)
                    db.commit()
                    
                    logger.info(
                        f"Packing completed: {len(items_to_pack)} items into "
                        f"{packing_result.total_bases} base(s), "
                        f"avg utilization: {packing_result.avg_utilization:.1f}%"
                    )
                    
                    # ===== Feature 10: Render PDFs =====
                    render_service = RenderService()
                    
                    # Prepare data for rendering
                    items_map = {item.id: item for item in items_to_pack}
                    assets_map = {}
                    for item in items_to_pack:
                        if item.asset_id and item.asset_id not in assets_map:
                            asset = db.query(Asset).filter(Asset.id == item.asset_id).first()
                            if asset:
                                assets_map[item.asset_id] = asset
                    
                    # Render all bases
                    pdf_uris = asyncio.run(render_service.render_bases(
                        job=job,
                        bases=packing_result.bases,
                        items_map=items_map,
                        assets_map=assets_map,
                        storage_driver=storage_driver
                    ))
                    
                    # Update manifest with output URIs
                    manifest["outputs"] = {
                        "pdfs": pdf_uris,
                        "previews": []  # Optional for MVP
                    }
                    manifest["completed_at"] = datetime.utcnow().isoformat()
                    
                    # Calculate processing time
                    if job.created_at:
                        processing_time = (datetime.utcnow() - job.created_at).total_seconds()
                        manifest["processing_time_seconds"] = round(processing_time, 2)
                    
                    job.manifest_json = json.dumps(manifest)
                    
                    # Mark job as completed
                    job.status = "completed"
                    job.completed_at = datetime.utcnow()
                    job.updated_at = datetime.utcnow()
                    db.commit()
                    
                    logger.info(
                        f"Job {job_id} completed successfully! "
                        f"Generated {len(pdf_uris)} PDF(s)"
                    )
                    
                except Exception as phase4_error:
                    logger.exception(f"Phase 4 error for job {job_id}: {str(phase4_error)}")
                    job.status = "failed"
                    manifest["error"] = f"Phase 4 failed: {str(phase4_error)}"
                    manifest["stage"] = "phase4"
                    job.manifest_json = json.dumps(manifest)
                    job.updated_at = datetime.utcnow()
                    db.commit()
                    raise
            
            return {
                "status": "success",
                "job_id": job_id,
                "items_parsed": len(parsed_items),
                "items_resolved": resolved_count,
                "items_missing": missing_count,
                "items_ambiguous": ambiguous_count,
                "job_status": job.status,
                "message": (
                    f"Job processing completed. Resolved: {resolved_count}, "
                    f"Missing: {missing_count}, Ambiguous: {ambiguous_count}"
                )
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.exception(f"Error processing job {job_id}: {str(e)}")
        
        # Try to update job status to failed
        try:
            db = SessionLocal()
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.manifest_json = json.dumps({"error": str(e), "stage": "unknown"})
                job.updated_at = datetime.utcnow()
                db.commit()
            db.close()
        except Exception as update_error:
            logger.exception(f"Failed to update job status: {str(update_error)}")
        
        # Re-raise to let Celery handle retry
        raise
