"""
STEM SPLITTER - Background Worker
Handles async processing to avoid request timeouts
"""

import os
import sys
import json
import threading
import traceback
from pathlib import Path
from datetime import datetime

# Job storage (in production, use Redis or a database)
JOBS = {}

class Job:
    def __init__(self, job_id, input_path, output_dir, options):
        self.job_id = job_id
        self.input_path = input_path
        self.output_dir = output_dir
        self.options = options
        self.status = "pending"
        self.progress = 0
        self.message = "Queued for processing"
        self.result = None
        self.error = None
        self.created_at = datetime.utcnow()
        self.completed_at = None
    
    def to_dict(self):
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


def process_job(job, run_demucs_func, convert_func, output_formats, sample_rates):
    """Process a separation job in a background thread."""
    try:
        job.status = "processing"
        job.progress = 5
        job.message = "Starting Demucs..."
        
        options = job.options
        model = options.get("model", "htdemucs")
        stems_filter = options.get("stems_filter")
        output_format = options.get("output_format", "wav_24bit")
        sample_rate = options.get("sample_rate")
        
        # Run separation
        job.progress = 10
        job.message = "Separating audio (this may take a few minutes)..."
        
        run_demucs_func(
            Path(job.input_path), 
            Path(job.output_dir), 
            model=model, 
            stems=stems_filter
        )
        
        job.progress = 80
        job.message = "Processing stems..."
        
        # Find the separated stems
        input_stem = Path(job.input_path).stem.replace(f"{job.job_id}_", "")
        stems_dir = Path(job.output_dir) / model / input_stem
        
        if not stems_dir.exists():
            # Try finding any subdirectory
            for subdir in (Path(job.output_dir) / model).iterdir():
                if subdir.is_dir():
                    stems_dir = subdir
                    break
        
        # Convert to requested format
        format_config = output_formats.get(output_format, {"ext": "wav", "codec": "pcm_s24le"})
        sample_rate_hz = sample_rates.get(sample_rate) if sample_rate else None
        requested_stems = options.get("requested_stems", "all")
        
        result_files = {}
        
        for stem_file in stems_dir.glob("*.wav"):
            stem_name = stem_file.stem
            
            # Handle instrumental request
            if requested_stems == "instrumental":
                if stem_name == "no_vocals":
                    stem_name = "instrumental"
                elif stem_name == "vocals":
                    continue
                else:
                    continue
            elif requested_stems != "all" and stem_name != requested_stems:
                if stem_name == "no_vocals":
                    continue
                continue
            
            if requested_stems == "all" and stem_name == "no_vocals":
                continue
            
            # Convert if needed
            if format_config.get("ext") == "wav" and not sample_rate_hz:
                result_files[stem_name] = str(stem_file)
            else:
                output_path = stem_file.with_suffix(f".{format_config['ext']}")
                convert_func(stem_file, output_path, format_config, sample_rate_hz)
                result_files[stem_name] = str(output_path)
        
        job.progress = 100
        job.status = "complete"
        job.message = "Separation complete!"
        job.completed_at = datetime.utcnow()
        
        # Build download URLs
        download_urls = {}
        for name, path in result_files.items():
            stem_filename = Path(path).name
            download_urls[name] = f"/api/download/{job.job_id}/{stem_filename}"
        
        job.result = {
            "stems": result_files,
            "download_urls": download_urls
        }
        
        # Cleanup input file
        try:
            if Path(job.input_path).exists():
                Path(job.input_path).unlink()
        except:
            pass
        
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.message = f"Failed: {str(e)[:100]}"
        job.completed_at = datetime.utcnow()
        print(f"❌ Job {job.job_id} failed: {e}")
        print(traceback.format_exc())


def start_job(job, run_demucs_func, convert_func, output_formats, sample_rates):
    """Start a job in a background thread."""
    JOBS[job.job_id] = job
    
    thread = threading.Thread(
        target=process_job,
        args=(job, run_demucs_func, convert_func, output_formats, sample_rates),
        daemon=True
    )
    thread.start()
    
    return job


def get_job(job_id):
    """Get job by ID."""
    return JOBS.get(job_id)


def cleanup_old_jobs(max_age_hours=24):
    """Remove old completed jobs from memory."""
    now = datetime.utcnow()
    to_remove = []
    
    for job_id, job in JOBS.items():
        if job.completed_at:
            age = (now - job.completed_at).total_seconds() / 3600
            if age > max_age_hours:
                to_remove.append(job_id)
    
    for job_id in to_remove:
        del JOBS[job_id]

