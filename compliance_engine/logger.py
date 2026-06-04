import logging
import sys

def configure_logging(log_level: str = "INFO"):
    """
    Sets up the default logging configuration for the compliance engine backend,
    formatting messages with clean time, status, and logger descriptors.
    """
    # Map input string level to logging level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Define a clean layout format
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s -> %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    if root_logger.handlers:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            
    # Stream Handler for console output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    console_handler.setLevel(numeric_level)
    root_logger.addHandler(console_handler)
    
    # Prevent propagation from other library verbose logs
    logging.getLogger("uvicorn.error").propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastembed").setLevel(logging.WARNING)
    logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
    
    logging.info(f"System logging configured at level: {log_level}")
