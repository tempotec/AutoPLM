import multiprocessing

# Server socket
bind = "0.0.0.0:5000"

# Workers — 2-4x CPU cores, min 2
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
worker_class = "gthread"
threads = 2

# Timeouts
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "/var/log/autoplm/access.log"
errorlog = "/var/log/autoplm/error.log"
loglevel = "info"

# Process naming
proc_name = "autoplm"

# Preload app for faster worker startup
preload_app = True

# Restart workers after N requests (prevent memory leaks)
max_requests = 1000
max_requests_jitter = 50
