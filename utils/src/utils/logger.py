from datetime import datetime



def _log(text: str, color: str, prefix: str = ""):
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    reset = "\033[0m"
    print(f"{color}[MIG | {time}] [{prefix:^7}] {text}{reset}")



def log_success(text: str) -> None:
    _log(text, "\033[32m", "SUCCESS")



def log_fail(text: str) -> None:
    _log(text, "\033[31m", "FAIL")



def log_warning(text: str) -> None:
    _log(text, "\033[33m", "WARNING")



def log_info(text: str) -> None:
    _log(text, "\033[36m", "INFO")