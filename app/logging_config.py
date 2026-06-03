import logging
import json
import sys
from datetime import datetime, timezone
from app.config import settings

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "filename": record.filename,
            "lineno": record.lineno,
        }
        
        # Add stack trace if exception occurred
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)
            
        # Add extra variables passed via extra={}
        extra_keys = set(record.__dict__.keys()) - {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName", "processName",
            "process"
        }
        for key in extra_keys:
            log_payload[key] = record.__dict__[key]
            
        return json.dumps(log_payload)

def setup_logging():
    log_level_str = settings.LOG_LEVEL.upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove default uvicorn handlers or root handlers to avoid double logging
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    
    # We can default to JSON logging to satisfy the "structured logging" requirement in a clean way,
    # or use normal human-readable formatting in development and JSON in production.
    if settings.ENV.lower() == "production":
        formatter = JSONFormatter()
    else:
        # A semi-structured format for development
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Configure uvicorn loggers to use our configuration
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = []
        logging_logger.propagate = True
