# 🎛️ STEM SPLITTER

### Audio Alchemy Laboratory
*"Splitting atoms... I mean, audio frequencies"*

A powerful, beautiful web application for separating audio tracks into individual stems using **Demucs** - Meta's state-of-the-art audio source separation model.

![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.9+-blue)
![Demucs](https://img.shields.io/badge/powered%20by-Demucs-orange)

---

## ✨ Features

- **🎯 Drag & Drop Interface** - Simply drag any audio file into the window
- **⚡ Multiple Quality Modes**
  - Lightning: Fast processing, good quality
  - Balanced: Default, optimal balance
  - Pristine: Best quality, fine-tuned model
  - 6-Stem: Adds piano and guitar separation
- **🎵 Flexible Stem Selection** - Extract all stems or just what you need (vocals, drums, bass, other)
- **📦 Multiple Output Formats** - WAV, FLAC, MP3 (320/256/192kbps), OGG
- **🖥️ GPU Acceleration** - Automatic detection of CUDA/MPS for faster processing
- **🎨 Beautiful Physics-Lab UI** - Oscilloscope-inspired dark theme

---

## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- FFmpeg (for format conversion)
- CUDA-capable GPU (optional, for faster processing)

### Installation

1. **Clone or download this project:**
```bash
cd demucs
```

2. **Create a virtual environment (recommended):**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Install FFmpeg** (if not already installed):
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows (using Chocolatey)
choco install ffmpeg
```

### Running the Application

```bash
python app.py
```

Then open your browser to: **http://localhost:5000**

---

## 🎛️ How It Works

### The Demucs Engine

This application uses **Demucs** (Deep Extractor for Music Sources), a deep learning model developed by Meta AI Research. It separates music into:

| Stem | Description |
|------|-------------|
| 🎤 **Vocals** | Lead and background vocals |
| 🥁 **Drums** | Percussion and drums |
| 🎸 **Bass** | Bass guitar and low frequencies |
| 🎹 **Other** | Everything else (synths, guitars, etc.) |

The 6-stem model additionally separates:
- 🎹 **Piano**
- 🎸 **Guitar**

### Processing Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Upload    │ ──▶ │   Demucs    │ ──▶ │   Convert   │ ──▶ │  Download   │
│   Audio     │     │   Separate  │     │   Format    │     │   Stems     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

---

## 🎚️ Quality Modes Explained

| Mode | Model | Speed | Quality | Use Case |
|------|-------|-------|---------|----------|
| ⚡ Lightning | htdemucs | Fast | Good | Quick previews |
| ◉ Balanced | htdemucs | Medium | Great | General use |
| ✦ Pristine | htdemucs_ft | Slow | Best | Final production |
| ❖ 6-Stem | htdemucs_6s | Slow | Great | Detailed separation |

---

## 📁 Supported Formats

### Input
MP3, WAV, FLAC, OGG, M4A, AAC, WMA, AIFF, OPUS

### Output
- **WAV** - Uncompressed, lossless
- **FLAC** - Compressed, lossless
- **MP3 320kbps** - High quality lossy
- **MP3 256kbps** - Standard quality
- **MP3 192kbps** - Smaller file size
- **OGG Vorbis** - Open format lossy

---

## 🖥️ System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| GPU | None | NVIDIA CUDA or Apple Silicon |
| Storage | 2 GB | 10+ GB (for temp files) |

### Processing Times (Approximate)

| Mode | CPU | GPU |
|------|-----|-----|
| Lightning | 2-3x realtime | 0.3x realtime |
| Balanced | 3-4x realtime | 0.5x realtime |
| Pristine | 5-6x realtime | 0.7x realtime |

*A 4-minute song at 0.5x realtime = ~2 minutes processing*

---

## 🔧 API Reference

### GET `/api/info`
Returns system information and available options.

### POST `/api/separate`
Main separation endpoint.

**Form Data:**
- `file`: Audio file (required)
- `quality`: `lightning` | `balanced` | `pristine` | `6stem`
- `format`: `wav` | `flac` | `mp3_320` | `mp3_256` | `mp3_192` | `ogg`
- `stems`: `all` | `vocals` | `drums` | `bass` | `other`

### GET `/api/download/<job_id>/<filename>`
Download a separated stem file.

### POST `/api/cleanup/<job_id>`
Clean up temporary files after download.

---

## 🆚 STEM SPLITTER vs LALAL.AI

| Feature | STEM SPLITTER | LALAL.AI |
|---------|---------------|----------|
| Price | **FREE** / One-time | $30+/month |
| Privacy | **Local processing** | Cloud upload |
| Quality | State-of-the-art | State-of-the-art |
| Speed | Depends on hardware | Fast (their servers) |
| Offline | ✅ Yes | ❌ No |
| Open Source | ✅ Yes | ❌ No |

---

## 🎨 Credits

- **Demucs** by Meta AI Research - [GitHub](https://github.com/facebookresearch/demucs)
- **Flask** - Web framework
- **FFmpeg** - Audio conversion
- UI Design inspired by physics laboratories and recording studios

---

## 📜 License

MIT License - Use it, modify it, ship it! 🚀

---

<p align="center">
  <strong>"For the underdog artist who deserves pristine samples"</strong>
  <br>
  Made with 💚 and way too much coffee
</p>

