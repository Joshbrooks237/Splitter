/**
 * STEM SPLITTER - Audio Alchemy Laboratory
 * Frontend JavaScript Controller
 */

class StemSplitter {
    constructor() {
        this.selectedFile = null;
        this.selectedUrl = null;  // URL mode
        this.urlMetadata = null;  // URL metadata
        this.inputMode = 'file';  // 'file' or 'url'
        this.jobId = null;
        this.stemsData = null;
        this.licenseInfo = null;
        this.deviceId = this.getOrCreateDeviceId();  // Persistent device ID
        
        this.init();
    }
    
    getOrCreateDeviceId() {
        /**
         * Generate a persistent device ID stored in localStorage.
         * This ensures the free trial countdown persists across browser refreshes.
         */
        const DEVICE_ID_KEY = 'stem_splitter_device_id';
        let deviceId = localStorage.getItem(DEVICE_ID_KEY);
        
        if (!deviceId) {
            // Generate a new UUID-like ID if it doesn't exist
            deviceId = 'device_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem(DEVICE_ID_KEY, deviceId);
        }
        
        return deviceId;
    }
    
    init() {
        this.cacheDOM();
        this.bindEvents();
        this.checkSystemStatus();
    }
    
    // Helper to send API requests with device ID and credentials
    async apiCall(endpoint, options = {}) {
        const headers = {
            'X-Device-ID': this.deviceId,
            ...(options.headers || {})  // Merge in any provided headers
        };
        
        const response = await fetch(endpoint, {
            ...options,
            headers,
            credentials: 'include'  // Always send cookies with requests
        });
        
        return response;
    }
    
    cacheDOM() {
        // Mode toggle
        this.fileModeBtn = document.getElementById('fileModeBtn');
        this.urlModeBtn = document.getElementById('urlModeBtn');
        
        // Drop zone (file mode)
        this.dropZone = document.getElementById('dropZone');
        this.fileInput = document.getElementById('fileInput');
        
        // URL zone (url mode)
        this.urlZone = document.getElementById('urlZone');
        this.urlInput = document.getElementById('urlInput');
        this.extractBtn = document.getElementById('extractBtn');
        this.urlStatus = document.getElementById('urlStatus');
        
        // URL info (shown after URL extracted)
        this.urlInfo = document.getElementById('urlInfo');
        this.urlThumbnail = document.getElementById('urlThumbnail');
        this.urlTitle = document.getElementById('urlTitle');
        this.urlUploader = document.getElementById('urlUploader');
        this.urlDuration = document.getElementById('urlDuration');
        this.clearUrl = document.getElementById('clearUrl');
        
        // File info
        this.fileInfo = document.getElementById('fileInfo');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');
        this.clearFile = document.getElementById('clearFile');
        this.waveformCanvas = document.getElementById('waveformCanvas');
        
        // Controls
        this.controlPanel = document.getElementById('controlPanel');
        this.processBtn = document.getElementById('processBtn');
        this.formatSelect = document.getElementById('formatSelect');
        
        // Processing state
        this.processingState = document.getElementById('processingState');
        this.processingStatus = document.getElementById('processingStatus');
        this.progressFill = document.getElementById('progressFill');
        
        // Results
        this.results = document.getElementById('results');
        this.stemsGrid = document.getElementById('stemsGrid');
        this.downloadAllBtn = document.getElementById('downloadAllBtn');
        this.newSessionBtn = document.getElementById('newSessionBtn');
        
        // Status
        this.deviceStatus = document.getElementById('deviceStatus');
    }
    
    bindEvents() {
        // Mode toggle
        if (this.fileModeBtn) {
            this.fileModeBtn.addEventListener('click', () => {
                this.setInputMode('file');
                // Also open file picker when clicking the Upload File button
                if (this.inputMode === 'file') {
                    this.fileInput.click();
                }
            });
        }
        if (this.urlModeBtn) {
            this.urlModeBtn.addEventListener('click', () => this.setInputMode('url'));
        }
        
        // Drag and drop
        this.dropZone.addEventListener('click', () => this.fileInput.click());
        this.dropZone.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.dropZone.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        this.dropZone.addEventListener('drop', (e) => this.handleDrop(e));
        
        // File input
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        
        // Clear file
        this.clearFile.addEventListener('click', () => this.resetToInitial());
        
        // URL mode events
        if (this.extractBtn) {
            this.extractBtn.addEventListener('click', () => this.handleUrlExtract());
        }
        if (this.urlInput) {
            this.urlInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.handleUrlExtract();
            });
        }
        if (this.clearUrl) {
            this.clearUrl.addEventListener('click', () => this.resetUrlMode());
        }
        
        // Process button
        if (this.processBtn) {
            this.processBtn.addEventListener('click', () => {
                console.log('🎵 Process button clicked!', {
                    inputMode: this.inputMode,
                    selectedFile: this.selectedFile ? this.selectedFile.name : null,
                    selectedUrl: this.selectedUrl,
                    buttonDisabled: this.processBtn.disabled
                });
                this.startProcessing();
            });
            console.log('✅ Process button event listener attached');
        } else {
            console.error('❌ Process button not found!');
        }
        
        // Results actions
        this.downloadAllBtn.addEventListener('click', () => this.downloadAllStems());
        this.newSessionBtn.addEventListener('click', () => this.startNewSession());
        
        // Format type buttons (filter dropdown)
        this.initFormatTypeButtons();
    }
    
    initFormatTypeButtons() {
        const buttons = document.querySelectorAll('.format-type-btn');
        const select = document.getElementById('formatSelect');
        
        const formatGroups = {
            'lossless': ['wav_', 'flac_', 'aiff_', 'alac'],
            'mp3': ['mp3_'],
            'aac': ['aac_'],
            'ogg': ['ogg_'],
            'opus': ['opus_'],
            'other': ['wma_', 'ac3_']
        };
        
        buttons.forEach(btn => {
            btn.addEventListener('click', () => {
                // Update active state
                buttons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                const type = btn.dataset.type;
                const prefixes = formatGroups[type];
                
                // Show/hide options and select first matching
                let firstMatch = null;
                Array.from(select.options).forEach(opt => {
                    const matches = prefixes.some(p => opt.value.startsWith(p));
                    opt.hidden = !matches;
                    if (matches && !firstMatch) {
                        firstMatch = opt.value;
                    }
                });
                
                // Show optgroups that have visible options
                Array.from(select.querySelectorAll('optgroup')).forEach(group => {
                    const hasVisible = Array.from(group.options).some(o => !o.hidden);
                    group.hidden = !hasVisible;
                });
                
                if (firstMatch) {
                    select.value = firstMatch;
                }
            });
        });
    }
    
    setInputMode(mode) {
        this.inputMode = mode;
        
        // Update toggle buttons
        if (this.fileModeBtn) {
            this.fileModeBtn.classList.toggle('active', mode === 'file');
        }
        if (this.urlModeBtn) {
            this.urlModeBtn.classList.toggle('active', mode === 'url');
        }
        
        // Show/hide appropriate zones
        if (mode === 'file') {
            if (this.dropZone) this.dropZone.classList.remove('hidden');
            if (this.urlZone) this.urlZone.classList.add('hidden');
            if (this.urlInfo) this.urlInfo.classList.add('hidden');
            // Reset URL state
            this.selectedUrl = null;
            this.urlMetadata = null;
        } else {
            if (this.dropZone) this.dropZone.classList.add('hidden');
            if (this.fileInfo) this.fileInfo.classList.add('hidden');
            if (this.urlZone) this.urlZone.classList.remove('hidden');
            // Reset file state
            this.selectedFile = null;
        }
        
        // Reset process button
        this.processBtn.disabled = true;
        
        console.log(`🔄 Input mode: ${mode}`);
    }
    
    async handleUrlExtract() {
        const url = this.urlInput?.value?.trim();
        
        if (!url) {
            this.showError('Please enter a URL');
            return;
        }
        
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            this.showError('URL must start with http:// or https://');
            return;
        }
        
        console.log('🔗 Extracting URL info:', url);
        
        // Show loading state
        if (this.extractBtn) {
            this.extractBtn.disabled = true;
            this.extractBtn.textContent = 'LOADING...';
        }
        if (this.urlStatus) {
            this.urlStatus.textContent = 'Fetching info...';
            this.urlStatus.className = 'url-status loading';
        }
        
        try {
            const response = await this.apiCall('/api/url-info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch URL info');
            }
            
            console.log('✅ URL info:', data);
            
            // Store URL metadata
            this.selectedUrl = url;
            this.urlMetadata = data;
            
            // Update UI
            if (this.urlZone) this.urlZone.classList.add('hidden');
            if (this.urlInfo) this.urlInfo.classList.remove('hidden');
            
            if (this.urlTitle) this.urlTitle.textContent = data.title || 'Unknown';
            if (this.urlUploader) this.urlUploader.textContent = data.uploader || '';
            if (this.urlDuration) this.urlDuration.textContent = data.duration_string || '';
            if (this.urlThumbnail && data.thumbnail) {
                this.urlThumbnail.src = data.thumbnail;
            }
            
            // Enable process button
            this.processBtn.disabled = false;
            
            // Clear status
            if (this.urlStatus) {
                this.urlStatus.textContent = '';
                this.urlStatus.className = 'url-status';
            }
            
        } catch (error) {
            console.error('❌ URL fetch error:', error);
            this.showError(error.message);
            
            if (this.urlStatus) {
                this.urlStatus.textContent = error.message;
                this.urlStatus.className = 'url-status error';
            }
        } finally {
            // Reset button
            if (this.extractBtn) {
                this.extractBtn.disabled = false;
                this.extractBtn.textContent = 'EXTRACT';
            }
        }
    }
    
    resetUrlMode() {
        this.selectedUrl = null;
        this.urlMetadata = null;
        
        if (this.urlInfo) this.urlInfo.classList.add('hidden');
        if (this.urlZone) this.urlZone.classList.remove('hidden');
        if (this.urlInput) this.urlInput.value = '';
        if (this.urlStatus) {
            this.urlStatus.textContent = '';
            this.urlStatus.className = 'url-status';
        }
        
        this.processBtn.disabled = true;
    }
    
    async checkSystemStatus() {
        try {
            const response = await this.apiCall('/api/info');
            const data = await response.json();
            
            const statusDot = this.deviceStatus.querySelector('.status-dot');
            const statusText = this.deviceStatus.querySelector('.status-text');
            
            statusDot.classList.add('active');
            statusText.textContent = data.device.toUpperCase() + ' Ready';
            
            // Store and display license info
            if (data.license) {
                this.licenseInfo = data.license;
                this.updateLicenseUI();
            }
            
            console.log('🎛️ System Status:', data);
            console.log('📜 License:', data.license);
        } catch (error) {
            console.error('Failed to fetch system info:', error);
            const statusText = this.deviceStatus.querySelector('.status-text');
            statusText.textContent = 'Offline';
        }
    }
    
    updateLicenseUI() {
        const licenseBar = document.getElementById('licenseBar');
        if (!licenseBar || !this.licenseInfo) return;
        
        const { is_trial, songs_processed, songs_remaining, is_licensed } = this.licenseInfo;
        
        if (is_licensed) {
            licenseBar.innerHTML = `
                <div class="license-status licensed">
                    <span class="license-icon">✓</span>
                    <span class="license-text">UNLIMITED LICENSE</span>
                </div>
            `;
            licenseBar.classList.add('licensed');
        } else {
            const remaining = songs_remaining;
            licenseBar.innerHTML = `
                <div class="license-status trial">
                    <span class="license-icon">🎁</span>
                    <span class="license-text">FREE TRIAL: ${remaining} song${remaining !== 1 ? 's' : ''} remaining</span>
                    <button class="btn-upgrade" onclick="window.stemSplitter.showUpgradeModal()">
                        Upgrade $5
                    </button>
                </div>
            `;
            licenseBar.classList.remove('licensed');
            
            if (remaining === 0) {
                licenseBar.classList.add('expired');
            }
        }
    }
    
    async showUpgradeModal() {
        // Create and show upgrade modal
        const modal = document.createElement('div');
        modal.className = 'upgrade-modal';
        modal.innerHTML = `
            <div class="upgrade-modal-content">
                <button class="modal-close" onclick="this.closest('.upgrade-modal').remove()">✕</button>
                <h2>🚀 UPGRADE TO UNLIMITED</h2>
                <p class="upgrade-price">$5 <span>one-time payment</span></p>
                
                <ul class="upgrade-features">
                    <li>✓ Unlimited stem separations forever</li>
                    <li>✓ All quality modes (Lightning → Pristine)</li>
                    <li>✓ All output formats & sample rates</li>
                    <li>✓ No watermarks, no limits</li>
                    <li>✓ Free updates for life</li>
                </ul>
                
                <button class="btn-checkout" onclick="window.stemSplitter.startCheckout()">
                    💳 Pay with Card
                </button>
                
                <div class="license-input-section">
                    <p>Already have a license key?</p>
                    <div class="license-input-row">
                        <input type="text" id="licenseKeyInput" placeholder="XXXX-XXXX-XXXX-XXXX">
                        <button onclick="window.stemSplitter.activateLicense()">Activate</button>
                    </div>
                </div>
                
                <p class="upgrade-note">Secure payment via Stripe. No subscription.</p>
            </div>
        `;
        
        document.body.appendChild(modal);
    }
    
    async startCheckout() {
        try {
            const response = await this.apiCall('/api/checkout', { method: 'POST' });
            const data = await response.json();
            
            if (data.checkout_url) {
                window.location.href = data.checkout_url;
            } else {
                this.showError(data.error || 'Failed to start checkout');
            }
        } catch (error) {
            this.showError('Payment error: ' + error.message);
        }
    }
    
    async activateLicense() {
        const input = document.getElementById('licenseKeyInput');
        const key = input.value.trim().toUpperCase();
        
        if (!key) {
            this.showError('Please enter a license key');
            return;
        }
        
        try {
            const response = await this.apiCall('/api/activate-license', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ license_key: key })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Update license info and UI
                this.licenseInfo = data.license;
                this.updateLicenseUI();
                
                // Close modal
                document.querySelector('.upgrade-modal')?.remove();
                
                // Show success
                this.showSuccess('License activated! Unlimited stems unlocked.');
            } else {
                this.showError(data.error || 'Invalid license key');
            }
        } catch (error) {
            this.showError('Activation error: ' + error.message);
        }
    }
    
    showSuccess(message) {
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #00ff88;
            color: #0a0b0f;
            padding: 1rem 2rem;
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 600;
            z-index: 1000;
            animation: fadeInUp 0.3s ease;
        `;
        toast.textContent = '✓ ' + message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
    
    handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        this.dropZone.classList.add('dragover');
    }
    
    handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        this.dropZone.classList.remove('dragover');
    }
    
    handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this.dropZone.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            this.selectFile(files[0]);
        }
    }
    
    handleFileSelect(e) {
        const files = e.target.files;
        if (files.length > 0) {
            this.selectFile(files[0]);
        }
    }
    
    selectFile(file) {
        // Accept virtually any audio/video format - FFmpeg will handle decoding
        const validTypes = [
            'audio/', 'video/',  // Any audio or video MIME type
        ];
        const validExtensions = [
            // Lossless
            'wav', 'flac', 'aiff', 'aif', 'alac', 'ape', 'wv', 'tta', 'dsd', 'dsf', 'dff',
            // Lossy
            'mp3', 'ogg', 'opus', 'm4a', 'aac', 'wma', 'mpc', 'mp2',
            // Container formats
            'webm', 'mka', 'mkv', 'mp4', 'mov', 'avi', 'wmv', 'flv',
            // Professional/Broadcast
            'ac3', 'eac3', 'dts', 'amr', 'gsm',
            // Vintage/Specialty
            'ra', 'ram', 'au', 'snd', 'voc', 'mid', 'midi',
            // Raw
            'raw', 'pcm'
        ];
        
        const extension = file.name.split('.').pop().toLowerCase();
        const isValidType = validTypes.some(type => file.type.startsWith(type));
        const isValidExt = validExtensions.includes(extension);
        
        if (!isValidType && !isValidExt) {
            this.showError('Unrecognized file type. Try anyway? Most audio formats are supported.');
            // Still allow it - let FFmpeg try
        }
        
        this.selectedFile = file;
        console.log('✅ File selected:', file.name, { size: file.size, type: file.type });
        this.showFileInfo();
        this.drawWaveformPlaceholder();
        this.processBtn.disabled = false;
        console.log('✅ Process button enabled:', { disabled: this.processBtn.disabled });
    }
    
    showFileInfo() {
        this.dropZone.classList.add('hidden');
        this.fileInfo.classList.remove('hidden');
        
        this.fileName.textContent = this.selectedFile.name;
        this.fileSize.textContent = this.formatFileSize(this.selectedFile.size);
    }
    
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    drawWaveformPlaceholder() {
        const canvas = this.waveformCanvas;
        const ctx = canvas.getContext('2d');
        
        // Set canvas size
        canvas.width = canvas.offsetWidth * 2;
        canvas.height = canvas.offsetHeight * 2;
        ctx.scale(2, 2);
        
        const width = canvas.offsetWidth;
        const height = canvas.offsetHeight;
        
        // Clear
        ctx.fillStyle = '#1a1d28';
        ctx.fillRect(0, 0, width, height);
        
        // Draw fake waveform
        ctx.strokeStyle = '#00ff88';
        ctx.lineWidth = 1;
        ctx.beginPath();
        
        const centerY = height / 2;
        const amplitude = height * 0.35;
        
        for (let x = 0; x < width; x++) {
            const y = centerY + Math.sin(x * 0.05) * amplitude * Math.random();
            if (x === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        
        ctx.stroke();
        
        // Add glow effect
        ctx.shadowColor = '#00ff88';
        ctx.shadowBlur = 10;
        ctx.stroke();
    }
    
    resetToInitial() {
        this.selectedFile = null;
        this.fileInfo.classList.add('hidden');
        this.dropZone.classList.remove('hidden');
        this.processBtn.disabled = true;
        this.fileInput.value = '';
    }
    
    getSelectedOptions() {
        const quality = document.querySelector('input[name="quality"]:checked')?.value || 'balanced';
        const stems = document.querySelector('input[name="stems"]:checked')?.value || 'all';
        const format = this.formatSelect.value;
        const sampleRate = document.querySelector('input[name="sampleRate"]:checked')?.value || '';
        
        return { quality, stems, format, sampleRate };
    }
    
    async startProcessing() {
        // Check we have something to process
        if (this.inputMode === 'file' && !this.selectedFile) return;
        if (this.inputMode === 'url' && !this.selectedUrl) return;
        
        const options = this.getSelectedOptions();
        
        // Show processing state
        this.controlPanel.classList.add('hidden');
        if (this.fileInfo) this.fileInfo.classList.add('hidden');
        if (this.urlInfo) this.urlInfo.classList.add('hidden');
        this.processingState.classList.remove('hidden');
        
        // Simulate progress
        this.simulateProgress();
        
        try {
            let result;
            
            if (this.inputMode === 'url') {
                // URL mode - send JSON
                this.updateProcessingStatus('Downloading audio from URL...');
                
                const response = await this.apiCall('/api/separate-url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url: this.selectedUrl,
                        quality: options.quality,
                        format: options.format,
                        stems: options.stems,
                        sample_rate: options.sampleRate || null
                    })
                });
                
                result = await response.json();
                
                if (!response.ok) {
                    if (response.status === 402 && result.trial_expired) {
                        this.showUpgradeModal();
                        throw new Error('Trial expired - upgrade to continue');
                    }
                    throw new Error(result.error || 'Failed to start processing');
                }
                
            } else {
                // File mode - send FormData
                this.updateProcessingStatus('Uploading audio file...');
                
                const formData = new FormData();
                formData.append('file', this.selectedFile);
                formData.append('quality', options.quality);
                formData.append('format', options.format);
                formData.append('stems', options.stems);
                if (options.sampleRate) {
                    formData.append('sample_rate', options.sampleRate);
                }
                
                // Don't set Content-Type header for FormData - browser will set it automatically
                const response = await this.apiCall('/api/separate', {
                    method: 'POST',
                    headers: {},  // Let browser set Content-Type for FormData
                    body: formData
                });
                
                result = await response.json();
                
                if (!response.ok) {
                    if (response.status === 402 && result.trial_expired) {
                        this.showUpgradeModal();
                        throw new Error('Trial expired - upgrade to continue');
                    }
                    throw new Error(result.error || 'Failed to start processing');
                }
            }
            
            this.jobId = result.job_id;
            console.log('🚀 Job started:', result.job_id);
            
            // Update license info
            if (result.license) {
                this.licenseInfo = result.license;
                this.updateLicenseUI();
            }
            
            // Poll for completion
            this.updateProcessingStatus('Processing audio (this may take a few minutes)...');
            const finalResult = await this.pollJobStatus(result.job_id);
            
            this.stemsData = finalResult;
            console.log('🎵 Processing complete:', finalResult);
            
            this.showResults();
            
        } catch (error) {
            console.error('Processing error:', error);
            this.showError(error.message);
            this.resetUI();
        }
    }
    
    async pollJobStatus(jobId) {
        const maxAttempts = 900; // 15 minutes at 1 second intervals (Demucs can take a while on CPU)
        let attempts = 0;
        
        while (attempts < maxAttempts) {
            attempts++;
            
            try {
                const response = await this.apiCall(`/api/job/${jobId}`);
                const job = await response.json();
                
                console.log(`📊 Job ${jobId} status: ${job.status} (${job.progress}%)`);
                
                // Update progress
                if (job.progress) {
                    this.progressFill.style.width = Math.min(job.progress, 95) + '%';
                }
                if (job.message) {
                    this.updateProcessingStatus(job.message);
                }
                
                if (job.status === 'complete') {
                    this.progressFill.style.width = '100%';
                    return job;
                }
                
                if (job.status === 'failed') {
                    throw new Error(job.error || 'Processing failed');
                }
                
                // Wait 1 second before polling again
                await new Promise(resolve => setTimeout(resolve, 1000));
                
            } catch (error) {
                console.error('Polling error:', error);
                // Don't throw immediately - might be a network glitch
                if (attempts > 5) {
                    throw error;
                }
                await new Promise(resolve => setTimeout(resolve, 2000));
            }
        }
        
        throw new Error('Processing timed out. Please try again.');
    }
    
    simulateProgress() {
        let progress = 0;
        const messages = [
            'Initializing Demucs neural network...',
            'Loading audio waveform...',
            'Analyzing frequency spectrum...',
            'Separating vocal frequencies...',
            'Isolating drum patterns...',
            'Extracting bass frequencies...',
            'Processing harmonic content...',
            'Finalizing stem separation...',
            'This may take a few minutes...',
            'Still working on it...',
            'Almost there...'
        ];
        
        const interval = setInterval(() => {
            progress += Math.random() * 15;
            if (progress > 95) progress = 95;
            
            this.progressFill.style.width = progress + '%';
            
            const messageIndex = Math.min(
                Math.floor(progress / 12),
                messages.length - 1
            );
            this.updateProcessingStatus(messages[messageIndex]);
            
            if (progress >= 95) {
                clearInterval(interval);
            }
        }, 800);
        
        this.progressInterval = interval;
    }
    
    updateProcessingStatus(message) {
        this.processingStatus.textContent = message;
    }
    
    showResults() {
        // Stop progress simulation
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }
        
        this.progressFill.style.width = '100%';
        
        setTimeout(() => {
            this.processingState.classList.add('hidden');
            this.results.classList.remove('hidden');
            
            this.renderStems();
        }, 500);
    }
    
    renderStems() {
        const stemIcons = {
            vocals: '🎤',
            instrumental: '🎶',
            drums: '🥁',
            bass: '🎸',
            other: '🎹',
            piano: '🎹',
            guitar: '🎸',
            no_vocals: '🎶'
        };
        
        this.stemsGrid.innerHTML = '';
        
        const { stems, download_urls } = this.stemsData;
        const format = this.formatSelect.value.split('_')[0].toUpperCase();
        
        console.log('🎵 Rendering stems:', Object.keys(stems));
        console.log('📥 Download URLs:', download_urls);
        
        for (const [stemName, filePath] of Object.entries(stems)) {
            const downloadUrl = download_urls[stemName];
            const card = document.createElement('div');
            card.className = 'stem-card';
            card.innerHTML = `
                <div class="stem-icon">${stemIcons[stemName] || '♫'}</div>
                <div class="stem-name">${stemName}</div>
                <div class="stem-format">${format}</div>
                <button class="stem-download" data-url="${downloadUrl}" data-name="${stemName}">
                    ↓ Download
                </button>
            `;
            
            // Add click handler for download button
            const btn = card.querySelector('.stem-download');
            btn.addEventListener('click', () => this.downloadStem(downloadUrl, stemName));
            
            this.stemsGrid.appendChild(card);
        }
    }
    
    async downloadStem(url, stemName) {
        const btn = document.querySelector(`[data-name="${stemName}"]`);
        if (btn) {
            btn.disabled = true;
            btn.textContent = '⏳ Loading...';
        }
        
        try {
            console.log(`📥 Downloading ${stemName} from ${url}`);
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'Accept': 'application/octet-stream, audio/*, */*'
                }
            });
            
            console.log(`📥 Response status: ${response.status}`);
            console.log(`📥 Content-Type: ${response.headers.get('Content-Type')}`);
            console.log(`📥 Content-Length: ${response.headers.get('Content-Length')}`);
            
            if (!response.ok) {
                // Try to get error message
                const text = await response.text();
                let errorMsg;
                try {
                    const json = JSON.parse(text);
                    errorMsg = json.error || json.message || `HTTP ${response.status}`;
                    console.error('Server error:', json);
                } catch {
                    errorMsg = text.substring(0, 100) || `HTTP ${response.status}`;
                }
                throw new Error(errorMsg);
            }
            
            // Get the blob
            if (btn) btn.textContent = '⏳ Receiving...';
            const blob = await response.blob();
            console.log(`📥 Received blob: ${blob.size} bytes, type: ${blob.type}`);
            
            if (blob.size === 0) {
                throw new Error('Received empty file');
            }
            
            // Get filename from Content-Disposition header or use default
            const contentDisposition = response.headers.get('Content-Disposition');
            let filename = `${stemName}.wav`;
            if (contentDisposition) {
                const match = contentDisposition.match(/filename="?([^"]+)"?/);
                if (match) filename = match[1];
            }
            
            // Create download link
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(downloadUrl);
            
            console.log(`✅ Downloaded ${stemName}: ${filename}`);
            if (btn) {
                btn.textContent = '✓ Downloaded';
                btn.disabled = false;
            }
            
        } catch (error) {
            console.error(`❌ Download error for ${stemName}:`, error);
            this.showError(`Failed to download ${stemName}: ${error.message}`);
            if (btn) {
                btn.textContent = '↓ Retry';
                btn.disabled = false;
            }
        }
    }
    
    async downloadAllStems() {
        if (!this.stemsData) return;
        
        const { download_urls } = this.stemsData;
        
        for (const [stemName, url] of Object.entries(download_urls)) {
            await this.downloadStem(url, stemName);
            // Small delay between downloads
            await new Promise(resolve => setTimeout(resolve, 500));
        }
    }
    
    async startNewSession() {
        // Cleanup server-side files
        if (this.jobId) {
            try {
                await this.apiCall(`/api/cleanup/${this.jobId}`, { method: 'POST' });
            } catch (e) {
                console.warn('Cleanup failed:', e);
            }
        }
        
        this.resetUI();
    }
    
    resetUI() {
        this.selectedFile = null;
        this.selectedUrl = null;
        this.urlMetadata = null;
        this.jobId = null;
        this.stemsData = null;
        
        this.results.classList.add('hidden');
        this.processingState.classList.add('hidden');
        if (this.fileInfo) this.fileInfo.classList.add('hidden');
        if (this.urlInfo) this.urlInfo.classList.add('hidden');
        
        // Show correct input zone based on mode
        if (this.inputMode === 'url') {
            if (this.dropZone) this.dropZone.classList.add('hidden');
            if (this.urlZone) this.urlZone.classList.remove('hidden');
            if (this.urlInput) this.urlInput.value = '';
        } else {
            if (this.dropZone) this.dropZone.classList.remove('hidden');
            if (this.urlZone) this.urlZone.classList.add('hidden');
        }
        
        this.controlPanel.classList.remove('hidden');
        
        this.progressFill.style.width = '0%';
        this.processBtn.disabled = true;
        this.fileInput.value = '';
    }
    
    showError(message) {
        // Create error toast
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #ff4757;
            color: white;
            padding: 1rem 2rem;
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            z-index: 1000;
            animation: fadeInUp 0.3s ease;
        `;
        toast.textContent = '⚠️ ' + message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    window.stemSplitter = new StemSplitter();
    console.log('🎵 STEM SPLITTER initialized');
    console.log('   "Splitting atoms... I mean, audio frequencies"');
});

