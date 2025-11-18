// Simple Toast Notification System
const Toast = {
    container: null,
    
    init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.id = 'toast-container';
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    },
    
    show(message, type = 'info', duration = 4000) {
        this.init();
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icon = this.getIcon(type);
        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
        `;
        
        this.container.appendChild(toast);
        
        // Animate in
        setTimeout(() => toast.classList.add('toast-show'), 10);
        
        // Auto remove
        if (duration > 0) {
            setTimeout(() => {
                toast.classList.remove('toast-show');
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }
        
        return toast;
    },
    
    getIcon(type) {
        const icons = {
            success: '<i class="fas fa-check-circle"></i>',
            error: '<i class="fas fa-exclamation-circle"></i>',
            warning: '<i class="fas fa-exclamation-triangle"></i>',
            info: '<i class="fas fa-info-circle"></i>',
            processing: '<i class="fas fa-spinner fa-spin"></i>'
        };
        return icons[type] || icons.info;
    },
    
    success(message, duration) {
        return this.show(message, 'success', duration);
    },
    
    error(message, duration) {
        return this.show(message, 'error', duration);
    },
    
    warning(message, duration) {
        return this.show(message, 'warning', duration);
    },
    
    info(message, duration) {
        return this.show(message, 'info', duration);
    },
    
    processing(message) {
        return this.show(message, 'processing', 0); // No auto-dismiss
    }
};

// Status polling helper
function pollSpecStatus(specId, onComplete) {
    const pollInterval = 2000; // Check every 2 seconds
    const maxAttempts = 150; // 5 minutes max
    let attempts = 0;
    
    const toast = Toast.processing('Processando arquivo em segundo plano...');
    
    const check = () => {
        attempts++;
        
        fetch(`/api/spec/status/${specId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const status = data.status || 'processing';
                    
                    if (status === 'completed') {
                        toast.remove();
                        Toast.success(`✓ Processamento concluído: ${data.description || 'Ficha técnica'}`);
                        if (onComplete) onComplete(data);
                    } else if (status === 'error') {
                        toast.remove();
                        Toast.error('❌ Erro no processamento. Verifique o arquivo.');
                        if (onComplete) onComplete(data);
                    } else if (status === 'processing' || !status) {
                        // Still processing, check again
                        if (attempts < maxAttempts) {
                            setTimeout(check, pollInterval);
                        } else {
                            // Timeout
                            toast.remove();
                            Toast.warning('⏱️ Processamento ainda em andamento. Recarregue a página para verificar.');
                        }
                    } else {
                        // Unknown status, keep checking
                        if (attempts < maxAttempts) {
                            setTimeout(check, pollInterval);
                        }
                    }
                } else {
                    toast.remove();
                    Toast.error('Erro ao verificar status: ' + (data.error || 'Desconhecido'));
                }
            })
            .catch(error => {
                console.error('Poll error:', error);
                // Don't remove toast on network errors, keep trying
                if (attempts < maxAttempts) {
                    setTimeout(check, pollInterval);
                } else {
                    toast.remove();
                    Toast.error('❌ Erro ao verificar status do processamento');
                }
            });
    };
    
    check();
}
