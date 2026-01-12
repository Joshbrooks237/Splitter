"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                        STEM SPLITTER - AUDIO ALCHEMY                          ║
║                     "Splitting atoms... I mean, audio"                        ║
║                                                                               ║
║  Powered by Demucs - The open-source audio separation engine from Meta       ║
║                                                                               ║
║  Pricing: 2 free songs → $5 once → Unlimited forever                         ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import uuid
import shutil
import subprocess
import traceback
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
import torch
import torchaudio

# Configure torchaudio backend for container compatibility
try:
    # Try soundfile first (uses libsndfile)
    torchaudio.set_audio_backend("soundfile")
    print("✅ Torchaudio backend: soundfile")
except Exception:
    try:
        # Fallback to sox_io
        torchaudio.set_audio_backend("sox_io")
        print("✅ Torchaudio backend: sox_io")
    except Exception as e:
        print(f"⚠️ Could not set torchaudio backend: {e}")

# Import licensing system
from licensing import (
    init_licensing, db, 
    get_or_create_device, require_processing_rights,
    activate_license_for_device, License,
    FREE_TRIAL_SONGS, PRODUCT_PRICE_USD
)

# Import async worker
from worker import Job, start_job, get_job

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "stem-splitter-dev-key-change-in-prod")

# Configure CORS properly for Railway deployment
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "http://localhost:8080",
            "http://localhost:5000",
            "http://127.0.0.1:8080",
            "http://127.0.0.1:5000",
            "https://splitter-production-0a43.up.railway.app",
            "https://*.up.railway.app",
            "*"  # Allow all for now - tighten in production
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
        "expose_headers": ["Content-Disposition", "Content-Length"],
        "supports_credentials": True
    }
})

# Initialize licensing/payment system
init_licensing(app)

# Configuration - Use absolute paths for Railway
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
OUTPUT_FOLDER = BASE_DIR / "outputs"

# Accept ALL audio formats FFmpeg can decode
ALLOWED_EXTENSIONS = {
    # Lossless
    'wav', 'flac', 'aiff', 'aif', 'alac', 'ape', 'wv', 'tta', 'dsd', 'dsf', 'dff',
    # Lossy
    'mp3', 'ogg', 'opus', 'm4a', 'aac', 'wma', 'mpc', 'mp2',
    # Container formats with audio
    'webm', 'mka', 'mkv', 'mp4', 'mov', 'avi', 'wmv', 'flv',
    # Professional/Broadcast
    'ac3', 'eac3', 'dts', 'amr', 'gsm',
    # Vintage/Specialty
    'ra', 'ram', 'au', 'snd', 'voc', 'sf2', 'mid', 'midi',
    # Raw formats
    'raw', 'pcm', 'f32le', 'f64le', 's16le', 's24le', 's32le',
}

# Create directories
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

# Demucs model options (quality tiers)
MODELS = {
    "lightning": "htdemucs",      # Fast, good quality
    "balanced": "htdemucs",       # Default, balanced
    "pristine": "htdemucs_ft",    # Fine-tuned, best quality
    "6stem": "htdemucs_6s",       # 6 stems (includes piano & guitar)
}

# Sample rate options (Hz)
SAMPLE_RATES = {
    "44100": 44100,   # CD Quality
    "48000": 48000,   # Professional/Video
    "88200": 88200,   # Hi-Res (2x CD)
    "96000": 96000,   # Hi-Res Studio
    "176400": 176400, # Hi-Res (4x CD)
    "192000": 192000, # Maximum Hi-Res
}

# Output format configurations - ALL formats, ALL resolutions
OUTPUT_FORMATS = {
    # === WAV (Uncompressed) ===
    "wav_16bit": {"ext": "wav", "codec": "pcm_s16le", "label": "WAV 16-bit (CD Quality)"},
    "wav_24bit": {"ext": "wav", "codec": "pcm_s24le", "label": "WAV 24-bit (Studio)"},
    "wav_32bit": {"ext": "wav", "codec": "pcm_s32le", "label": "WAV 32-bit (Maximum)"},
    "wav_32float": {"ext": "wav", "codec": "pcm_f32le", "label": "WAV 32-bit Float (Pro)"},
    
    # === FLAC (Lossless Compressed) ===
    "flac_16bit": {"ext": "flac", "codec": "flac", "sample_fmt": "s16", "label": "FLAC 16-bit"},
    "flac_24bit": {"ext": "flac", "codec": "flac", "sample_fmt": "s32", "label": "FLAC 24-bit"},
    
    # === AIFF (Apple Lossless) ===
    "aiff_16bit": {"ext": "aiff", "codec": "pcm_s16be", "label": "AIFF 16-bit"},
    "aiff_24bit": {"ext": "aiff", "codec": "pcm_s24be", "label": "AIFF 24-bit"},
    
    # === ALAC (Apple Lossless Codec) ===
    "alac": {"ext": "m4a", "codec": "alac", "label": "ALAC (Apple Lossless)"},
    
    # === MP3 (Lossy) ===
    "mp3_320": {"ext": "mp3", "codec": "libmp3lame", "bitrate": "320k", "label": "MP3 320 kbps (Best)"},
    "mp3_256": {"ext": "mp3", "codec": "libmp3lame", "bitrate": "256k", "label": "MP3 256 kbps"},
    "mp3_192": {"ext": "mp3", "codec": "libmp3lame", "bitrate": "192k", "label": "MP3 192 kbps"},
    "mp3_128": {"ext": "mp3", "codec": "libmp3lame", "bitrate": "128k", "label": "MP3 128 kbps"},
    "mp3_v0": {"ext": "mp3", "codec": "libmp3lame", "quality": "0", "label": "MP3 V0 (VBR Best)"},
    "mp3_v2": {"ext": "mp3", "codec": "libmp3lame", "quality": "2", "label": "MP3 V2 (VBR High)"},
    
    # === AAC/M4A (Modern Lossy) ===
    "aac_256": {"ext": "m4a", "codec": "aac", "bitrate": "256k", "label": "AAC 256 kbps"},
    "aac_192": {"ext": "m4a", "codec": "aac", "bitrate": "192k", "label": "AAC 192 kbps"},
    "aac_128": {"ext": "m4a", "codec": "aac", "bitrate": "128k", "label": "AAC 128 kbps"},
    
    # === OGG Vorbis ===
    "ogg_q10": {"ext": "ogg", "codec": "libvorbis", "quality": "10", "label": "OGG Vorbis Q10 (Best)"},
    "ogg_q8": {"ext": "ogg", "codec": "libvorbis", "quality": "8", "label": "OGG Vorbis Q8"},
    "ogg_q6": {"ext": "ogg", "codec": "libvorbis", "quality": "6", "label": "OGG Vorbis Q6"},
    "ogg_q4": {"ext": "ogg", "codec": "libvorbis", "quality": "4", "label": "OGG Vorbis Q4"},
    
    # === OPUS (Modern, Efficient) ===
    "opus_256": {"ext": "opus", "codec": "libopus", "bitrate": "256k", "label": "OPUS 256 kbps"},
    "opus_192": {"ext": "opus", "codec": "libopus", "bitrate": "192k", "label": "OPUS 192 kbps"},
    "opus_128": {"ext": "opus", "codec": "libopus", "bitrate": "128k", "label": "OPUS 128 kbps"},
    "opus_96": {"ext": "opus", "codec": "libopus", "bitrate": "96k", "label": "OPUS 96 kbps"},
    "opus_64": {"ext": "opus", "codec": "libopus", "bitrate": "64k", "label": "OPUS 64 kbps (Voice)"},
    
    # === WMA (Windows Media) ===
    "wma_192": {"ext": "wma", "codec": "wmav2", "bitrate": "192k", "label": "WMA 192 kbps"},
    "wma_128": {"ext": "wma", "codec": "wmav2", "bitrate": "128k", "label": "WMA 128 kbps"},
    
    # === AC3 (Dolby Digital) ===
    "ac3_448": {"ext": "ac3", "codec": "ac3", "bitrate": "448k", "label": "AC3 448 kbps (DVD)"},
    "ac3_384": {"ext": "ac3", "codec": "ac3", "bitrate": "384k", "label": "AC3 384 kbps"},
    "ac3_256": {"ext": "ac3", "codec": "ac3", "bitrate": "256k", "label": "AC3 256 kbps"},
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_device():
    """Detect best available device for processing."""
    try:
        if torch.cuda.is_available():
            return "cuda"
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return "mps"  # Apple Silicon
    except Exception as e:
        print(f"⚠️ Device detection error: {e}")
    return "cpu"


def convert_audio_format(input_path, output_path, format_config, sample_rate=None):
    """Convert audio file to desired format using ffmpeg."""
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]
    
    # Sample rate (Hz) - must come before codec
    if sample_rate:
        cmd.extend(["-ar", str(sample_rate)])
    
    # Audio codec
    if format_config.get("codec"):
        cmd.extend(["-acodec", format_config["codec"]])
    
    # Bitrate (CBR)
    if format_config.get("bitrate"):
        cmd.extend(["-b:a", format_config["bitrate"]])
    
    # Quality (VBR) - for codecs that support -q:a
    if format_config.get("quality"):
        cmd.extend(["-q:a", format_config["quality"]])
    
    # Sample format (bit depth for FLAC)
    if format_config.get("sample_fmt"):
        cmd.extend(["-sample_fmt", format_config["sample_fmt"]])
    
    # Ensure proper container format
    ext = format_config.get("ext", "wav")
    if ext == "m4a":
        cmd.extend(["-f", "ipod"])  # Proper M4A container
    elif ext == "opus":
        cmd.extend(["-f", "opus"])
    
    cmd.append(str(output_path))
    
    subprocess.run(cmd, capture_output=True, check=True)


def ensure_model_downloaded(model="htdemucs"):
    """Pre-download the Demucs model to avoid timeout during separation."""
    print(f"🔄 Ensuring model {model} is downloaded...")
    
    try:
        # Import demucs and trigger model download
        from demucs.pretrained import get_model
        from demucs.apply import BagOfModels
        import torch
        
        # This will download the model if not cached
        models = get_model(model)
        print(f"✅ Model {model} ready")
        return True
    except Exception as e:
        print(f"⚠️ Model pre-download failed: {e}")
        # Continue anyway - demucs CLI will try to download
        return False


def run_demucs(input_path, output_dir, model="htdemucs", stems=None):
    """
    Run Demucs separation on an audio file.
    
    Args:
        input_path: Path to input audio file
        output_dir: Directory to save separated stems
        model: Demucs model to use
        stems: List of specific stems to extract (None = all)
    
    Returns:
        Path to the output directory containing stems
    """
    device = get_device()
    
    # Check if we're in a low-memory environment (Railway, etc.)
    # Use memory-efficient settings
    is_cloud = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PORT")
    
    # Model selection - use lighter model in cloud if needed
    if is_cloud and model in ["htdemucs_ft", "htdemucs_6s"]:
        print(f"⚠️ Downgrading {model} to htdemucs for cloud compatibility")
        model = "htdemucs"
    
    # Pre-download model to avoid timeout during separation
    ensure_model_downloaded(model)
    
    # Use sys.executable to ensure we use the same Python as Flask
    cmd = [
        sys.executable, "-m", "demucs",
        "--out", str(output_dir),
        "-d", device,
    ]
    
    # Memory optimization for cloud environments
    if is_cloud:
        cmd.extend([
            "--segment", "7",      # Smaller segments = less RAM (default is ~40)
            "--overlap", "0.1",    # Less overlap = less RAM
            "--jobs", "1",         # Single job = less RAM
            "--mp3",               # Use MP3 output (lameenc) to bypass torchaudio.save() bug
            "--mp3-bitrate", "320", # High quality MP3
        ])
        print("☁️ Cloud mode: Using memory-efficient settings + MP3 output")
    
    cmd.extend(["--name", model])
    
    # Add two-stem mode for specific extractions
    # This creates "vocals" and "no_vocals" (instrumental) stems
    if stems and len(stems) == 1:
        if stems[0] in ["vocals", "instrumental"]:
            cmd.extend(["--two-stems", "vocals"])
        elif stems[0] == "drums":
            cmd.extend(["--two-stems", "drums"])
        elif stems[0] == "bass":
            cmd.extend(["--two-stems", "bass"])
    
    cmd.append(str(input_path))
    
    print(f"🎛️ Running Demucs:")
    print(f"   Command: {' '.join(cmd)}")
    print(f"   Input: {input_path} ({input_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"   Output: {output_dir}")
    print(f"   Device: {device}")
    print(f"   Model: {model}")
    
    # Set environment for better compatibility
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    env['OMP_NUM_THREADS'] = '2'  # Allow some parallelism
    env['MKL_NUM_THREADS'] = '2'
    env['TORCHAUDIO_USE_BACKEND_DISPATCHER'] = '1'  # Use new backend system
    
    try:
        # Use Popen with streaming to avoid buffer deadlock
        print(f"   Starting Demucs process...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Merge stderr into stdout
            text=True,
            env=env,
            bufsize=1  # Line buffered
        )
        
        # Stream output in real-time
        output_lines = []
        start_time = time.time()
        timeout_seconds = 1800  # 30 minutes
        
        while True:
            # Check timeout
            if time.time() - start_time > timeout_seconds:
                process.kill()
                raise Exception("Processing timed out. Try a shorter audio file.")
            
            # Read line (non-blocking with timeout)
            try:
                line = process.stdout.readline()
                if line:
                    line = line.strip()
                    output_lines.append(line)
                    print(f"   [Demucs] {line}")
                elif process.poll() is not None:
                    # Process finished
                    break
            except Exception as read_err:
                print(f"   Read error: {read_err}")
                if process.poll() is not None:
                    break
        
        # Get return code
        return_code = process.wait()
        
        print(f"   Demucs finished with code: {return_code}")
        print(f"   Duration: {time.time() - start_time:.1f}s")
        
        if return_code != 0:
            error_msg = '\n'.join(output_lines[-10:]) if output_lines else "Unknown error"
            
            # Check for common errors
            if "out of memory" in error_msg.lower() or "oom" in error_msg.lower():
                raise Exception("Out of memory. Try a shorter audio file (under 3 minutes) or use Lightning mode.")
            elif "killed" in error_msg.lower():
                raise Exception("Process killed (likely out of memory). Try a shorter audio file.")
            else:
                raise Exception(f"Separation failed: {error_msg[:300]}")
        
        return output_dir
        
    except subprocess.TimeoutExpired:
        raise Exception("Processing timed out. Try a shorter audio file.")
    except MemoryError:
        raise Exception("Out of memory. Try a shorter audio file (under 3 minutes).")


@app.route("/")
def index():
    """Serve the main application."""
    return render_template("index.html")


@app.route("/api/info")
def info():
    """Return system info and available options."""
    device_hw = get_device()
    user_device = get_or_create_device()
    
    return jsonify({
        "device": device_hw,
        "gpu_available": device_hw != "cpu",
        "models": list(MODELS.keys()),
        "formats": list(OUTPUT_FORMATS.keys()),
        "sample_rates": list(SAMPLE_RATES.keys()),
        "stems": ["vocals", "instrumental", "drums", "bass", "other", "all"],
        # Licensing info
        "license": {
            "is_trial": user_device.is_trial,
            "is_licensed": not user_device.is_trial,
            "songs_processed": user_device.songs_processed,
            "songs_remaining": user_device.songs_remaining if user_device.is_trial else "unlimited",
            "free_trial_total": FREE_TRIAL_SONGS,
            "upgrade_price_usd": PRODUCT_PRICE_USD / 100,
        }
    })


@app.route("/api/separate", methods=["POST"])
@require_processing_rights
def separate():
    """
    ASYNC separation endpoint - returns immediately, poll /api/job/<id> for status.
    
    Accepts:
        - audio file (multipart form)
        - quality: lightning | balanced | pristine | 6stem
        - format: wav | mp3_320 | mp3_256 | mp3_192 | flac | ogg
        - stems: vocals | drums | bass | other | all
    
    Returns:
        - job_id: Poll /api/job/<job_id> for status
    """
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400
    
    # Get options
    quality = request.form.get("quality", "balanced")
    output_format = request.form.get("format", "wav_24bit")
    requested_stems = request.form.get("stems", "all")
    sample_rate = request.form.get("sample_rate", None)  # None = keep original
    
    # Validate options
    if quality not in MODELS:
        return jsonify({"error": f"Invalid quality. Options: {', '.join(MODELS.keys())}"}), 400
    
    if output_format not in OUTPUT_FORMATS:
        return jsonify({"error": f"Invalid format. Options: {', '.join(OUTPUT_FORMATS.keys())}"}), 400
    
    if sample_rate and sample_rate not in SAMPLE_RATES:
        return jsonify({"error": f"Invalid sample rate. Options: {', '.join(SAMPLE_RATES.keys())}"}), 400
    
    # Validate options
    if quality not in MODELS:
        return jsonify({"error": f"Invalid quality. Options: {', '.join(MODELS.keys())}"}), 400
    
    # Create unique job ID
    job_id = str(uuid.uuid4())[:8]
    
    # Save uploaded file
    filename = secure_filename(file.filename)
    input_path = UPLOAD_FOLDER / f"{job_id}_{filename}"
    file.save(input_path)
    
    # Create output directory
    job_output_dir = OUTPUT_FOLDER / job_id
    job_output_dir.mkdir(parents=True, exist_ok=True)
    
    # Prepare job options
    model = MODELS[quality]
    stems_filter = None if requested_stems == "all" else [requested_stems]
    
    job_options = {
        "model": model,
        "stems_filter": stems_filter,
        "output_format": output_format,
        "sample_rate": sample_rate,
        "requested_stems": requested_stems,
    }
    
    # Create and start async job
    job = Job(
        job_id=job_id,
        input_path=str(input_path),
        output_dir=str(job_output_dir),
        options=job_options
    )
    
    # Increment usage counter now (optimistic)
    device = request.device
    device.songs_processed += 1
    if device.license:
        device.license.total_songs_processed += 1
    db.session.commit()
    
    # Start background processing
    start_job(job, run_demucs, convert_audio_format, OUTPUT_FORMATS, SAMPLE_RATES)
    
    print(f"🚀 Job {job_id} started in background")
    
    # Return immediately with job ID
    return jsonify({
        "job_id": job_id,
        "status": "processing",
        "message": "Processing started. Poll /api/job/{job_id} for status.",
        "poll_url": f"/api/job/{job_id}",
        "license": {
            "is_trial": device.is_trial,
            "songs_processed": device.songs_processed,
            "songs_remaining": device.songs_remaining if device.is_trial else "unlimited",
        }
    })


@app.route("/api/job/<job_id>")
def job_status(job_id):
    """Get status of a processing job."""
    job = get_job(job_id)
    
    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    response = job.to_dict()
    
    # Add download URLs if complete
    if job.status == "complete" and job.result:
        response["stems"] = job.result.get("stems", {})
        response["download_urls"] = job.result.get("download_urls", {})
    
    return jsonify(response)


@app.route("/api/download/<job_id>/<filename>")
def download(job_id, filename):
    """Download a separated stem file with streaming support."""
    from flask import Response
    import mimetypes
    
    print(f"📥 Download request: job={job_id}, file={filename}")
    
    # Light sanitization - don't use secure_filename on the full path
    # as it might break valid filenames with special chars
    job_id = job_id.replace("..", "").replace("/", "")
    filename = filename.replace("..", "").replace("/", "")
    
    job_dir = OUTPUT_FOLDER / job_id
    
    print(f"   Looking in: {job_dir}")
    print(f"   Job dir exists: {job_dir.exists()}")
    
    if not job_dir.exists():
        print(f"   ❌ Job directory not found")
        return jsonify({"error": "Job not found", "path": str(job_dir)}), 404
    
    # Find the file in the job directory
    file_path = None
    try:
        for model_dir in job_dir.iterdir():
            if model_dir.is_dir():
                for stem_dir in model_dir.iterdir():
                    if stem_dir.is_dir():
                        candidate = stem_dir / filename
                        print(f"   Checking: {candidate} exists={candidate.exists()}")
                        if candidate.exists():
                            file_path = candidate
                            break
                if file_path:
                    break
    except Exception as e:
        print(f"   ❌ Error searching: {e}")
        return jsonify({"error": f"Search error: {str(e)}"}), 500
    
    if not file_path or not file_path.exists():
        # List what files DO exist for debugging
        existing_files = []
        try:
            for root, dirs, files in os.walk(job_dir):
                for f in files:
                    existing_files.append(os.path.join(root, f))
        except:
            pass
        print(f"   ❌ File not found. Existing files: {existing_files}")
        return jsonify({
            "error": "File not found",
            "requested": filename,
            "existing_files": existing_files[:10]  # First 10
        }), 404
    
    # Get file info
    file_size = file_path.stat().st_size
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type is None:
        mime_type = 'application/octet-stream'
    
    print(f"   ✅ Found: {file_path} ({file_size / 1024 / 1024:.1f} MB, {mime_type})")
    
    # For large files, use streaming response
    def generate():
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                yield chunk
    
    response = Response(
        generate(),
        mimetype=mime_type,
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(file_size),
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length',
            'Cache-Control': 'no-cache',
        }
    )
    
    print(f"   📤 Sending response...")
    return response


@app.route("/api/cleanup/<job_id>", methods=["POST"])
def cleanup(job_id):
    """Clean up job files after download."""
    job_id = secure_filename(job_id)
    job_dir = OUTPUT_FOLDER / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    return jsonify({"status": "cleaned"})


@app.route("/api/debug/job/<job_id>")
def debug_job(job_id):
    """Debug endpoint to check job files exist."""
    job_id = secure_filename(job_id)
    job_dir = OUTPUT_FOLDER / job_id
    
    if not job_dir.exists():
        return jsonify({"exists": False, "path": str(job_dir)})
    
    files = []
    for root, dirs, filenames in os.walk(job_dir):
        for f in filenames:
            files.append(os.path.join(root, f))
    
    return jsonify({
        "exists": True,
        "path": str(job_dir),
        "files": files
    })


@app.route("/api/test-ytdlp")
def test_ytdlp():
    """
    Diagnostic endpoint to test if yt-dlp works on this server.
    Call this to debug URL extraction issues.
    """
    import json as json_module
    
    result = {
        "test": "yt-dlp",
        "steps": [],
        "success": False
    }
    
    # Step 1: Check if yt-dlp module exists
    try:
        result["steps"].append("Checking yt-dlp installation...")
        check = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if check.returncode == 0:
            result["yt_dlp_version"] = check.stdout.strip()
            result["steps"].append(f"✅ yt-dlp version: {check.stdout.strip()}")
        else:
            result["steps"].append(f"❌ yt-dlp check failed: {check.stderr}")
            return jsonify(result)
    except Exception as e:
        result["steps"].append(f"❌ yt-dlp not installed: {e}")
        return jsonify(result)
    
    # Step 2: Try to fetch info from a known working URL
    try:
        result["steps"].append("Testing URL extraction (Rick Astley - short timeout)...")
        test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",
            "--no-warnings",
            "--socket-timeout", "15",
            test_url
        ]
        
        fetch = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if fetch.returncode == 0:
            info = json_module.loads(fetch.stdout)
            result["steps"].append(f"✅ Got info: {info.get('title', 'Unknown')}")
            result["test_title"] = info.get("title")
            result["test_duration"] = info.get("duration")
            result["success"] = True
        else:
            result["steps"].append(f"❌ Extraction failed: {fetch.stderr[:200]}")
            result["stderr"] = fetch.stderr[:500]
            
    except subprocess.TimeoutExpired:
        result["steps"].append("❌ Extraction timed out after 30s")
    except json_module.JSONDecodeError as e:
        result["steps"].append(f"❌ JSON parse error: {e}")
    except Exception as e:
        result["steps"].append(f"❌ Extraction error: {e}")
    
    return jsonify(result)


@app.route("/api/preload-model")
def preload_model_endpoint():
    """Manually trigger model download."""
    model = request.args.get("model", "htdemucs")
    
    try:
        from demucs.pretrained import get_model
        print(f"🔄 Downloading model: {model}")
        get_model(model)
        return jsonify({"success": True, "model": model, "message": "Model downloaded successfully"})
    except Exception as e:
        return jsonify({"success": False, "model": model, "error": str(e)}), 500


@app.route("/api/ping")
def ping():
    """Simple ping endpoint to verify server is alive."""
    return jsonify({"status": "ok", "message": "pong"})


@app.route("/api/health")
def health_check():
    """Health check endpoint with system diagnostics."""
    import shutil as sh
    
    is_cloud = os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PORT")
    
    diagnostics = {
        "status": "ok",
        "environment": "cloud" if is_cloud else "local",
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "device": get_device(),
        "torch_version": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "base_dir": str(BASE_DIR),
        "upload_folder_exists": UPLOAD_FOLDER.exists(),
        "output_folder_exists": OUTPUT_FOLDER.exists(),
    }
    
    # Memory info (psutil is optional)
    try:
        import psutil
        mem = psutil.virtual_memory()
        diagnostics["memory_total_gb"] = round(mem.total / (1024**3), 2)
        diagnostics["memory_available_gb"] = round(mem.available / (1024**3), 2)
        diagnostics["memory_percent_used"] = mem.percent
    except ImportError:
        diagnostics["memory_info"] = "psutil not installed"
    except Exception as e:
        diagnostics["memory_error"] = str(e)
    
    # Check yt-dlp
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        diagnostics["ytdlp_installed"] = result.returncode == 0
        if result.returncode == 0:
            diagnostics["ytdlp_version"] = result.stdout.strip()
    except Exception as e:
        diagnostics["ytdlp_installed"] = False
        diagnostics["ytdlp_error"] = str(e)
    
    # Check if demucs is installed
    try:
        result = subprocess.run(
            [sys.executable, "-m", "demucs", "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        diagnostics["demucs_installed"] = result.returncode == 0
        if result.returncode != 0:
            diagnostics["demucs_error"] = result.stderr[:200]
    except Exception as e:
        diagnostics["demucs_installed"] = False
        diagnostics["demucs_error"] = str(e)
    
    # Check if model is cached
    try:
        from demucs.pretrained import SOURCES
        import torch
        model_dir = torch.hub.get_dir()
        diagnostics["model_cache_dir"] = model_dir
        
        # Check for htdemucs
        htdemucs_path = Path(model_dir) / "checkpoints" / "demucs"
        if htdemucs_path.exists():
            cached_models = list(htdemucs_path.glob("*.th"))
            diagnostics["cached_models"] = [m.name for m in cached_models]
        else:
            diagnostics["cached_models"] = []
            diagnostics["model_warning"] = "No models cached. First separation will download ~80MB model."
    except Exception as e:
        diagnostics["model_cache_error"] = str(e)
    
    # Check if ffmpeg is installed
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        diagnostics["ffmpeg_installed"] = result.returncode == 0
        if result.returncode == 0:
            diagnostics["ffmpeg_version"] = result.stdout.split('\n')[0][:50]
    except Exception as e:
        diagnostics["ffmpeg_installed"] = False
        diagnostics["ffmpeg_error"] = str(e)
    
    # Check disk space
    try:
        total, used, free = sh.disk_usage("/")
        diagnostics["disk_free_gb"] = round(free / (1024**3), 2)
        diagnostics["disk_total_gb"] = round(total / (1024**3), 2)
    except:
        pass
    
    # Recommendations
    if diagnostics.get("memory_available_gb", 0) < 4:
        diagnostics["warning"] = "Low memory. Use short audio files (under 3 min) and Lightning mode."
    
    return jsonify(diagnostics)


@app.route("/api/test-demucs")
def test_demucs():
    """Quick test to verify Demucs can start."""
    import tempfile
    import numpy as np
    import soundfile as sf
    
    result = {
        "test": "demucs_quick_start",
        "steps": []
    }
    
    try:
        # Step 1: Create a tiny test audio file (1 second of silence)
        result["steps"].append("Creating test audio...")
        test_dir = tempfile.mkdtemp()
        test_file = os.path.join(test_dir, "test.wav")
        
        # 1 second of near-silence at 44.1kHz
        audio_data = np.random.randn(44100) * 0.001
        sf.write(test_file, audio_data, 44100)
        result["steps"].append(f"Created {os.path.getsize(test_file)} byte test file")
        
        # Step 2: Try to run Demucs (with 30 second timeout)
        result["steps"].append("Starting Demucs...")
        
        cmd = [
            sys.executable, "-m", "demucs",
            "--two-stems", "vocals",
            "--out", test_dir,
            "-n", "htdemucs",
            "--segment", "5",
            test_file
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Wait up to 60 seconds for a response
        start = time.time()
        output_lines = []
        
        while time.time() - start < 60:
            line = process.stdout.readline()
            if line:
                output_lines.append(line.strip())
                result["steps"].append(f"[Demucs] {line.strip()}")
                # If we see "Separated" or "100%", it's working
                if "separated" in line.lower() or "100%" in line:
                    result["status"] = "success"
                    result["message"] = "Demucs is working!"
                    break
            if process.poll() is not None:
                break
        
        return_code = process.poll()
        if return_code is None:
            process.kill()
            result["status"] = "timeout"
            result["message"] = "Demucs started but didn't complete in 60s (which is expected for test)"
        elif return_code == 0:
            result["status"] = "success"
            result["message"] = "Demucs completed successfully!"
        else:
            result["status"] = "failed"
            result["message"] = f"Demucs exited with code {return_code}"
        
        result["output"] = output_lines[-20:] if output_lines else []
        
        # Cleanup
        shutil.rmtree(test_dir, ignore_errors=True)
        
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
    
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════════════
# URL EXTRACTION ENDPOINTS (YouTube, SoundCloud, Bandcamp, etc.)
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/url-info", methods=["POST"])
def url_info():
    """
    Fetch metadata about a URL (title, duration, thumbnail) without downloading.
    Uses yt-dlp CLI for stability (library can crash the server).
    """
    import json as json_module
    
    data = request.get_json()
    url = data.get("url", "").strip()
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Basic URL validation
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL - must start with http:// or https://"}), 400
    
    print(f"🔗 Fetching URL info: {url}")
    
    try:
        # Use yt-dlp CLI instead of library (more stable, won't crash server)
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-json",
            "--no-download",
            "--no-playlist",  # Only get single video, not entire playlist
            "--no-warnings",
            "--socket-timeout", "20",
            url
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=45  # 45 second timeout
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            print(f"   ❌ yt-dlp error: {error_msg[:200]}")
            
            # Friendly error messages
            if "Unsupported URL" in error_msg:
                return jsonify({"error": "This URL is not supported. Try YouTube, SoundCloud, Bandcamp, etc."}), 400
            elif "Video unavailable" in error_msg or "Private video" in error_msg:
                return jsonify({"error": "This video is unavailable or private."}), 400
            elif "Sign in" in error_msg:
                return jsonify({"error": "This content requires login and cannot be accessed."}), 400
            else:
                return jsonify({"error": f"Could not fetch URL: {error_msg[:100]}"}), 400
        
        # Parse JSON output
        info = json_module.loads(result.stdout)
        
        # Format duration
        duration = info.get("duration", 0)
        if duration:
            mins, secs = divmod(int(duration), 60)
            duration_string = f"{mins}:{secs:02d}"
        else:
            duration_string = ""
        
        response = {
            "title": info.get("title", "Unknown"),
            "duration": duration,
            "duration_string": duration_string,
            "thumbnail": info.get("thumbnail", ""),
            "uploader": info.get("uploader", info.get("channel", "")),
            "extractor": info.get("extractor", ""),
            "url": url,
        }
        
        print(f"   ✅ Found: {response['title']} ({duration_string})")
        return jsonify(response)
        
    except subprocess.TimeoutExpired:
        print(f"   ❌ URL fetch timed out")
        return jsonify({"error": "Request timed out. Please try again."}), 504
    except json_module.JSONDecodeError as e:
        print(f"   ❌ JSON parse error: {e}")
        return jsonify({"error": "Failed to parse URL info"}), 500
    except Exception as e:
        print(f"   ❌ URL info error: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Error: {str(e)[:100]}"}), 500


@app.route("/api/separate-url", methods=["POST"])
@require_processing_rights
def separate_url():
    """
    Download audio from URL and start stem separation.
    Uses yt-dlp CLI for stability.
    """
    import json as json_module
    
    data = request.get_json()
    url = data.get("url", "").strip()
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    # Get options
    quality = data.get("quality", "balanced")
    output_format = data.get("format", "wav_24bit")
    requested_stems = data.get("stems", "all")
    sample_rate = data.get("sample_rate", None)
    
    # Validate options
    if quality not in MODELS:
        return jsonify({"error": f"Invalid quality. Options: {', '.join(MODELS.keys())}"}), 400
    
    if output_format not in OUTPUT_FORMATS:
        return jsonify({"error": f"Invalid format. Options: {', '.join(OUTPUT_FORMATS.keys())}"}), 400
    
    if sample_rate and sample_rate not in SAMPLE_RATES:
        return jsonify({"error": f"Invalid sample rate. Options: {', '.join(SAMPLE_RATES.keys())}"}), 400
    
    # Create unique job ID
    job_id = str(uuid.uuid4())[:8]
    
    print(f"🔗 Downloading audio from URL: {url}")
    
    try:
        # Download audio using yt-dlp CLI (more stable than library)
        output_template = str(UPLOAD_FOLDER / f"{job_id}_url_audio")
        
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "192K",
            "--output", output_template + ".%(ext)s",
            "--no-playlist",  # Only download single video, not entire playlist
            "--no-warnings",
            "--socket-timeout", "60",
            "--retries", "3",
            "--print", "after_move:filepath",  # Print final path
            url
        ]
        
        print(f"   Running: {' '.join(cmd[:8])}...")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # 3 minute timeout for download
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Download failed"
            print(f"   ❌ yt-dlp download error: {error_msg[:200]}")
            return jsonify({"error": f"Download failed: {error_msg[:100]}"}), 500
        
        # Find the downloaded file
        actual_path = None
        
        # First try the printed filepath
        if result.stdout.strip():
            printed_path = Path(result.stdout.strip().split('\n')[-1])
            if printed_path.exists():
                actual_path = printed_path
        
        # Fallback: search for the file
        if not actual_path:
            for f in UPLOAD_FOLDER.glob(f"{job_id}_url_audio*"):
                if f.is_file() and f.suffix in ['.mp3', '.m4a', '.webm', '.opus', '.wav']:
                    actual_path = f
                    break
        
        if not actual_path or not actual_path.exists():
            print(f"   ❌ Downloaded file not found")
            print(f"   stdout: {result.stdout[:200]}")
            print(f"   stderr: {result.stderr[:200]}")
            return jsonify({"error": "Failed to download audio from URL"}), 500
        
        input_path = actual_path
        print(f"   ✅ Downloaded: {input_path.name} ({input_path.stat().st_size / 1024 / 1024:.1f} MB)")
        
        # Get title from a quick info fetch
        title = "audio"
        try:
            info_cmd = [sys.executable, "-m", "yt_dlp", "--dump-json", "--no-download", url]
            info_result = subprocess.run(info_cmd, capture_output=True, text=True, timeout=15)
            if info_result.returncode == 0:
                info = json_module.loads(info_result.stdout)
                title = info.get("title", "audio")
        except:
            pass  # Title is optional
        
        # Create output directory
        job_output_dir = OUTPUT_FOLDER / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare job options
        model = MODELS[quality]
        stems_filter = None if requested_stems == "all" else [requested_stems]
        
        job_options = {
            "model": model,
            "stems_filter": stems_filter,
            "output_format": output_format,
            "sample_rate": sample_rate,
            "requested_stems": requested_stems,
            "source_url": url,
            "source_title": title,
        }
        
        # Create and start async job
        job = Job(
            job_id=job_id,
            input_path=str(input_path),
            output_dir=str(job_output_dir),
            options=job_options
        )
        
        # Increment usage counter
        device = request.device
        device.songs_processed += 1
        if device.license:
            device.license.total_songs_processed += 1
        db.session.commit()
        
        # Start background processing
        start_job(job, run_demucs, convert_audio_format, OUTPUT_FORMATS, SAMPLE_RATES)
        
        print(f"🚀 URL Job {job_id} started in background")
        
        return jsonify({
            "job_id": job_id,
            "status": "processing",
            "title": title,
            "message": "Processing started. Poll /api/job/{job_id} for status.",
            "poll_url": f"/api/job/{job_id}",
            "license": {
                "is_trial": device.is_trial,
                "songs_processed": device.songs_processed,
                "songs_remaining": device.songs_remaining if device.is_trial else "unlimited",
            }
        })
        
    except subprocess.TimeoutExpired:
        print(f"   ❌ Download timed out")
        return jsonify({"error": "Download timed out. Try a shorter video."}), 504
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ URL separation error: {error_msg}")
        traceback.print_exc()
        return jsonify({"error": f"Failed to process URL: {error_msg[:200]}"}), 500


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


# ═══════════════════════════════════════════════════════════════════════════════
# PAYMENT & LICENSING ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/checkout", methods=["POST"])
def checkout():
    """
    Return the pre-built Stripe payment link for the $5 one-time payment.
    """
    # Use the pre-built Stripe payment link for $5
    checkout_url = "https://buy.stripe.com/28E9ASeFxeY024m39i8ww00"

    return jsonify({
        "checkout_url": checkout_url
    })


@app.route("/success")
def payment_success():
    """
    Payment success page - verify payment and show license key.
    """
    session_id = request.args.get('session_id')
    license_key = request.args.get('license_key')
    
    if session_id:
        # Verify the payment
        success, result = handle_successful_payment(session_id)
        if success:
            license_key = result
    
    return render_template("success.html", license_key=license_key)




@app.route("/api/claim-license", methods=["POST"])
def claim_license():
    """
    Claim a license after successful payment.
    Generates and activates a new license key.
    """
    data = request.get_json()
    email = data.get('email', '').strip()

    if not email:
        return jsonify({"error": "Email address is required"}), 400

    try:
        # Generate new license
        license_key = License.generate_key()

        # Create license record (already active since payment completed)
        license = License(
            key=license_key,
            email=email,
            is_active=True
        )
        db.session.add(license)

        # Create transaction record for tracking
        transaction = Transaction(
            license_key=license_key,
            amount_cents=PRODUCT_PRICE_USD,
            currency='usd',
            status='completed'
        )
        db.session.add(transaction)

        db.session.commit()

        return jsonify({
            "success": True,
            "license_key": license_key,
            "message": "License created and activated successfully"
        })

    except Exception as e:
        db.session.rollback()
        app.logger.error(f"License claim failed: {str(e)}")
        return jsonify({"error": "Failed to create license"}), 500


@app.route("/api/activate-license", methods=["POST"])
def activate_license():
    """
    Activate a license key for the current device.
    """
    data = request.get_json()
    license_key = data.get('license_key', '').strip().upper()

    if not license_key:
        return jsonify({"error": "No license key provided"}), 400

    device = get_or_create_device()
    success, message = activate_license_for_device(device, license_key)

    if success:
        return jsonify({
            "success": True,
            "message": message,
            "license": {
                "is_trial": False,
                "is_licensed": True,
                "songs_remaining": "unlimited"
            }
        })
    else:
        return jsonify({
            "success": False,
            "error": message
        }), 400




@app.route("/api/license-status")
def license_status():
    """
    Get current license/trial status for the device.
    """
    device = get_or_create_device()
    
    return jsonify({
        "is_trial": device.is_trial,
        "is_licensed": not device.is_trial,
        "songs_processed": device.songs_processed,
        "songs_remaining": device.songs_remaining if device.is_trial else "unlimited",
        "free_trial_total": FREE_TRIAL_SONGS,
        "can_process": device.can_process,
        "upgrade_price_usd": PRODUCT_PRICE_USD / 100,
    })


def preload_models():
    """Pre-download models on startup to avoid timeout during requests."""
    print("🔄 Pre-loading Demucs models...")
    try:
        from demucs.pretrained import get_model
        
        # Download the default model
        print("   Downloading htdemucs...")
        get_model("htdemucs")
        print("   ✅ htdemucs ready")
        
        return True
    except Exception as e:
        print(f"   ⚠️ Model preload failed: {e}")
        print("   Models will download on first use")
        return False


if __name__ == "__main__":
    # Get port from environment (Railway sets PORT)
    port = int(os.getenv("PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                     STEM SPLITTER                             ║
    ║              Audio Separation Laboratory                      ║
    ║                                                               ║
    ║  Device: {get_device().upper():.<48}║
    ║  Port: {port:<50}║
    ║  Debug: {str(debug):<49}║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Ensure directories exist
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    
    # Pre-download models on startup (avoids timeout during requests)
    preload_models()
    
    app.run(debug=debug, host="0.0.0.0", port=port)

