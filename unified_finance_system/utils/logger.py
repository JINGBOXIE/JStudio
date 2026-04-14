import logging
import os
from datetime import datetime

class Logger:
    def __init__(self, log_file="audit.log"):
        # 1. 创建日志器
        self.logger = logging.getLogger("FinanceSystem")
        self.logger.setLevel(logging.INFO)

        # 防止重复添加处理器（如果是单例模式）
        if not self.logger.handlers:
            # 2. 定义日志格式： 时间 - 级别 - 消息
            formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # 3. 控制台处理器：在终端实时显示
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

            # 4. 文件处理器：持久化记录到本地
            # 确保日志文件在根目录或指定位置
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def info(self, message):
        self.logger.info(message)

    def error(self, message):
        self.logger.error(message)

    def warning(self, message):
        self.logger.warning(message)

    def critical(self, message):
        self.logger.critical(message)

# 测试代码
if __name__ == "__main__":
    log = Logger()
    log.info("System Logger initialized.")
    log.error("This is a sample error message.")