"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║                        STEM SPLITTER - AUDIO ALCHEMY                          ║
║                     "Splitting atoms... I mean, audio"                        ║
║                                                                               ║
║  Powered by Demucs - The open-source audio separation engine from Meta       ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import uuid
import shutil
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import torch

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = Path("uploads")
OUTPUT_FOLDER = Path("outputs")

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
    if torch.cuda.is_available():
        return "cuda"
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return "mps"  # Apple Silicon
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
    
    cmd = [
        "python", "-m", "demucs",
        "--out", str(output_dir),
        "--name", model,
        "-d", device,
    ]
    
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
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"Demucs failed: {result.stderr}")
    
    return output_dir


@app.route("/")
def index():
    """Serve the main application."""
    return render_template("index.html")


@app.route("/api/info")
def info():
    """Return system info and available options."""
    device = get_device()
    return jsonify({
        "device": device,
        "gpu_available": device != "cpu",
        "models": list(MODELS.keys()),
        "formats": list(OUTPUT_FORMATS.keys()),
        "sample_rates": list(SAMPLE_RATES.keys()),
        "stems": ["vocals", "instrumental", "drums", "bass", "other", "all"],
    })


@app.route("/api/separate", methods=["POST"])
def separate():
    """
    Main separation endpoint.
    
    Accepts:
        - audio file (multipart form)
        - quality: lightning | balanced | pristine | 6stem
        - format: wav | mp3_320 | mp3_256 | mp3_192 | flac | ogg
        - stems: vocals | drums | bass | other | all
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
    
    # Convert sample rate to int if provided
    sample_rate_hz = SAMPLE_RATES.get(sample_rate) if sample_rate else None
    
    # Create unique job ID
    job_id = str(uuid.uuid4())[:8]
    
    # Save uploaded file
    filename = secure_filename(file.filename)
    input_path = UPLOAD_FOLDER / f"{job_id}_{filename}"
    file.save(input_path)
    
    try:
        # Run separation
        job_output_dir = OUTPUT_FOLDER / job_id
        model = MODELS[quality]
        
        stems_filter = None if requested_stems == "all" else [requested_stems]
        
        run_demucs(input_path, job_output_dir, model=model, stems=stems_filter)
        
        # Find the separated stems
        stem_name = input_path.stem.replace(f"{job_id}_", "")
        stems_dir = job_output_dir / model / stem_name
        
        if not stems_dir.exists():
            # Try finding any subdirectory
            for subdir in (job_output_dir / model).iterdir():
                if subdir.is_dir():
                    stems_dir = subdir
                    break
        
        # Convert to requested format if needed
        format_config = OUTPUT_FORMATS[output_format]
        result_files = {}
        
        for stem_file in stems_dir.glob("*.wav"):
            stem_name = stem_file.stem
            
            # Handle instrumental request - we want "no_vocals" renamed to "instrumental"
            if requested_stems == "instrumental":
                if stem_name == "no_vocals":
                    stem_name = "instrumental"  # Rename for clarity
                elif stem_name == "vocals":
                    continue  # Skip vocals when instrumental requested
                else:
                    continue
            elif requested_stems != "all" and stem_name != requested_stems:
                # For "no_vocals" stem, skip it unless specifically requesting instrumental
                if stem_name == "no_vocals":
                    continue
                continue
            
            # Skip "no_vocals" in "all" mode - user probably wants labeled stems
            if requested_stems == "all" and stem_name == "no_vocals":
                continue
            
            # Always convert if sample rate specified, or if format != wav
            if format_config["ext"] == "wav" and not sample_rate_hz:
                result_files[stem_name] = str(stem_file)
            else:
                output_path = stem_file.with_suffix(f".{format_config['ext']}")
                convert_audio_format(stem_file, output_path, format_config, sample_rate_hz)
                result_files[stem_name] = str(output_path)
        
        return jsonify({
            "job_id": job_id,
            "status": "complete",
            "stems": result_files,
            "download_urls": {
                name: f"/api/download/{job_id}/{Path(path).name}"
                for name, path in result_files.items()
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    finally:
        # Cleanup input file
        if input_path.exists():
            input_path.unlink()


@app.route("/api/download/<job_id>/<filename>")
def download(job_id, filename):
    """Download a separated stem file."""
    # Find the file
    for model_dir in (OUTPUT_FOLDER / job_id).iterdir():
        if model_dir.is_dir():
            for stem_dir in model_dir.iterdir():
                if stem_dir.is_dir():
                    file_path = stem_dir / filename
                    if file_path.exists():
                        return send_file(
                            file_path,
                            as_attachment=True,
                            download_name=filename
                        )
    
    return jsonify({"error": "File not found"}), 404


@app.route("/api/cleanup/<job_id>", methods=["POST"])
def cleanup(job_id):
    """Clean up job files after download."""
    job_dir = OUTPUT_FOLDER / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    return jsonify({"status": "cleaned"})


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                     STEM SPLITTER                             ║
    ║              Audio Separation Laboratory                      ║
    ║                                                               ║
    ║  Device: """ + get_device().upper() + """                                              ║
    ║  Server: http://localhost:8080                                ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    app.run(debug=True, host="0.0.0.0", port=8080)

