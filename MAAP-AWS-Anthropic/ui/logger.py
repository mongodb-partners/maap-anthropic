import asyncio
import logging
import os
import time
from httpx import AsyncClient, HTTPStatusError


class AsyncRemoteLogger:
    """
    A singleton asynchronous and synchronous remote logger that logs messages both locally and to a remote service.

    Attributes:
        service_url (str): The URL of the remote logging service.
        app_name (str): The name of the application using the logger.
        log_dir (str): The directory where local log files are stored.
        client (AsyncClient): The HTTP client used for sending logs to the remote service.
        local_logger (logging.Logger): The local fallback logger.

    Methods:
        __new__(cls, *args, **kwargs):
            Ensures that only one instance of the logger is created (singleton pattern).

        _init_logger(self, service_url: str, app_name: str, log_dir: str = "logs"):
            Initializes the logger with the given service URL, application name, and log directory.

        cleanup_old_logs(self):
            Removes log files older than 3 days from the log directory.

        Asynchronous Methods:
            async alog(self, level: str, message: str):
                Logs a message with the specified level both locally and to the remote service.

            async ainfo(self, message: str):
                Logs an informational message.

            async adebug(self, message: str):
                Logs a debug message.

            async awarning(self, message: str):
                Logs a warning message.

            async aerror(self, message: str):
                Logs an error message.

            async acritical(self, message: str):
                Logs a critical message.

            async aprint(self, *args, sep=" ", end="\n"):
                Logs a message with the INFO level, formatted similarly to the built-in print function.

            async aclose(self):
                Closes the HTTP client used for remote logging.

        Synchronous Methods:
            log(self, level: str, message: str):
                Synchronously logs a message with the specified level both locally and to the remote service.

            info(self, message: str):
                Synchronously logs an informational message.

            debug(self, message: str):
                Synchronously logs a debug message.

            warning(self, message: str):
                Synchronously logs a warning message.

            error(self, message: str):
                Synchronously logs an error message.

            critical(self, message: str):
                Synchronously logs a critical message.

            print(self, *args, sep=" ", end="\n"):
                Synchronously logs a message with the INFO level, formatted similarly to the built-in print function.

            close(self):
                Synchronously closes the HTTP client used for remote logging.

    Author:
        Mohammad Daoud Farooqi
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        # Ensure only one instance of the logger is created (singleton pattern)
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._init_logger(*args, **kwargs)
        return cls._instance

    def _init_logger(self, service_url: str, app_name: str, log_dir: str = "logs"):
        # Initialize the logger with the given service URL, application name, and log directory
        self.service_url = service_url
        self.app_name = app_name
        self.client = AsyncClient(timeout=10.0)
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.cleanup_old_logs()

        # Set up the local logger
        self.local_logger = logging.getLogger(app_name)
        self.local_logger.setLevel(logging.INFO)
        handler = logging.FileHandler(os.path.join(self.log_dir, f"{app_name}.log"))
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        self.local_logger.addHandler(handler)

    def cleanup_old_logs(self):
        # Remove log files older than 3 days from the log directory
        now = time.time()
        three_days_ago = now - (3 * 24 * 60 * 60)
        for filename in os.listdir(self.log_dir):
            file_path = os.path.join(self.log_dir, filename)
            if os.path.isfile(file_path):
                file_creation_time = os.path.getctime(file_path)
                if file_creation_time < three_days_ago:
                    try:
                        os.remove(file_path)
                        print(f"Removed old log file: {file_path}")
                    except Exception as e:
                        print(f"Error removing file {file_path}: {e}")

    # Asynchronous methods
    async def alog(self, level: str, message: str):
        # Log a message with the specified level both locally and to the remote service
        log_method = getattr(self.local_logger, level.lower(), None)
        if log_method:
            log_method(message)
        else:
            self.local_logger.error(f"Invalid log level: {level}. Message: {message}")

        try:
            response = await self.client.post(
                f"{self.service_url}/log",
                json={"level": level, "message": str(message), "app_name": self.app_name},
            )
            response.raise_for_status()
        except HTTPStatusError as e:
            self.local_logger.error(f"HTTP error during remote logging: {e}")
        except Exception as e:
            self.local_logger.error(f"Error sending log to the remote service: {e}")

    async def ainfo(self, message: str):
        # Log an informational message asynchronously
        await self.alog("INFO", message)

    async def adebug(self, message: str):
        # Log a debug message asynchronously
        await self.alog("DEBUG", message)

    async def awarning(self, message: str):
        # Log a warning message asynchronously
        await self.alog("WARNING", message)

    async def aerror(self, message: str):
        # Log an error message asynchronously
        await self.alog("ERROR", message)

    async def acritical(self, message: str):
        # Log a critical message asynchronously
        await self.alog("CRITICAL", message)

    async def aprint(self, *args, sep=" ", end="\n"):
        # Log a message with the INFO level, formatted similarly to the built-in print function
        message = sep.join(map(str, args)) + end.strip()
        print(message, sep, end)
        await self.ainfo(message)

    async def aclose(self):
        # Close the HTTP client used for remote logging
        await self.client.aclose()

    # Synchronous methods
    def _run_in_thread_or_loop(self, coro):
        # Run the coroutine in the current event loop or create a new one if none exists
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(coro)  # Running within an existing event loop
        except RuntimeError:
            # No running event loop; create and run one
            asyncio.run(coro)

    def log(self, level: str, message: str):
        # Synchronously log a message with the specified level both locally and to the remote service
        self._run_in_thread_or_loop(self.alog(level, message))

    def info(self, message: str):
        # Synchronously log an informational message
        self._run_in_thread_or_loop(self.ainfo(message))

    def debug(self, message: str):
        # Synchronously log a debug message
        self._run_in_thread_or_loop(self.adebug(message))

    def warning(self, message: str):
        # Synchronously log a warning message
        self._run_in_thread_or_loop(self.awarning(message))

    def error(self, message: str):
        # Synchronously log an error message
        self._run_in_thread_or_loop(self.aerror(message))

    def critical(self, message: str):
        # Synchronously log a critical message
        self._run_in_thread_or_loop(self.acritical(message))

    def print(self, *args, sep=" ", end="\n"):
        # Synchronously log a message with the INFO level, formatted similarly to the built-in print function
        message = sep.join(map(str, args)) + end.strip()
        print(message, sep, end)
        self._run_in_thread_or_loop(self.aprint(*args, sep=sep, end=end))

    def close(self):
        # Synchronously close the HTTP client used for remote logging
        self._run_in_thread_or_loop(self.aclose())
