"""
应用配置管理

使用 pydantic-settings 从环境变量加载配置
"""

from pathlib import Path


class Config:
    """应用配置类"""

    # ==================== Flask 配置 ====================
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    DEBUG: bool = False
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB
    SESSION_LIFETIME_DAYS: int = 7

    # ==================== 目录配置 ====================
    BASE_DIR: Path = Path(__file__).parent.parent
    UPLOAD_FOLDER: str = str(BASE_DIR / "uploads")
    OUTPUT_FOLDER: str = str(BASE_DIR / "output")
    STATIC_FOLDER: str = str(BASE_DIR / "static")
    TEMPLATES_FOLDER: str = str(BASE_DIR / "templates")

    # ==================== 数据库配置 ====================
    DB_TYPE: str = "sqlite"  # sqlite | mysql
    DB_PATH: str = "generation_records.db"

    # MySQL 配置
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "ai_generator"
    MYSQL_CHARSET: str = "utf8mb4"

    # ==================== 火山引擎配置 ====================
    VOLCENGINE_AK: str = ""
    VOLCENGINE_SK: str = ""

    # ==================== 阿里云 OSS 配置 ====================
    OSS_ENABLED: bool = False
    OSS_ENDPOINT: str = "shor-file.oss-cn-wulanchabu.aliyuncs.com"
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""

    # ==================== OpenAI 配置 ====================
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-3.5-turbo"

    # ==================== 火山方舟 / Seedance 配置 ====================
    ARK_API_KEY: str = ""
    ARK_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    SEEDANCE_OMNI_MODEL: str = "doubao-seedance-2-0-260128"
    SEEDANCE_OMNI_CREATE_PATH: str = "/contents/generations/tasks"
    SEEDANCE_OMNI_QUERY_PATH: str = "/contents/generations/tasks/{task_id}"
    SEEDANCE_OMNI_LIST_PATH: str = "/contents/generations/tasks"
    SEEDANCE_OMNI_CANCEL_PATH: str = "/contents/generations/tasks/{task_id}"

    # ==================== 火山方舟国际版 / Seedance 国际版配置 ====================
    ARK_INTL_API_KEY: str = ""
    ARK_INTL_BASE_URL: str = "https://ark.ap-southeast.bytepluses.com/api/v3"
    SEEDANCE_INTL_MODEL: str = "dreamina-seedance-2-0-260128"

    # ==================== 视频画质增强配置 ====================
    VIDEO_ENHANCE_API_KEY: str = ""
    VIDEO_ENHANCE_BASE_URL: str = "https://amk.cn-beijing.volces.com/api/v1"
    VIDEO_ENHANCE_CREATE_PATH: str = "/tools/enhance-video"
    VIDEO_ENHANCE_QUERY_PATH: str = "/tasks/{task_id}"

    # ==================== 脚本/分镜配置 ====================
    SCRIPT_MAX_LENGTH: int = 50000
    STORYBOARD_MAX_LENGTH: int = 100000

    # ==================== 文件上传配置 ====================
    ALLOWED_IMAGE_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    ALLOWED_VIDEO_EXTENSIONS: set = {".mp4", ".mov", ".avi", ".webm"}
    ALLOWED_AUDIO_EXTENSIONS: set = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
    ALLOWED_TEXT_EXTENSIONS: set = {".txt", ".md", ".json"}
    MAX_IMAGE_SIZE: int = 10 * 1024 * 1024  # 10MB
    MAX_VIDEO_SIZE: int = 500 * 1024 * 1024  # 500MB
    MAX_AUDIO_SIZE: int = 100 * 1024 * 1024  # 100MB
    MAX_TEXT_SIZE: int = 1 * 1024 * 1024  # 1MB

    # ==================== 日志配置 ====================
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "app.log"
    OPERATION_LOG_DIR: str = "logs/operations"

    # ==================== 视觉服务配置 ====================
    VISUAL_API_REGION: str = "cn-north-1"
    VISUAL_SERVICE_NAME: str = "cv"

    def __init__(self):
        """初始化配置，从环境变量加载"""
        import os

        # Flask 配置
        self.SECRET_KEY = os.environ.get("SECRET_KEY", self.SECRET_KEY)
        self.DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
        self.MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", self.MAX_CONTENT_LENGTH))

        # 数据库配置
        self.DB_TYPE = os.environ.get("DB_TYPE", self.DB_TYPE).lower()
        self.DB_PATH = os.environ.get("DB_PATH", self.DB_PATH)

        # MySQL 配置
        self.MYSQL_HOST = os.environ.get("MYSQL_HOST", self.MYSQL_HOST)
        self.MYSQL_PORT = int(os.environ.get("MYSQL_PORT", self.MYSQL_PORT))
        self.MYSQL_USER = os.environ.get("MYSQL_USER", self.MYSQL_USER)
        self.MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", self.MYSQL_PASSWORD)
        self.MYSQL_DATABASE = os.environ.get("MYSQL_DATABASE", self.MYSQL_DATABASE)
        self.MYSQL_CHARSET = os.environ.get("MYSQL_CHARSET", self.MYSQL_CHARSET)

        # 火山引擎配置
        self.VOLCENGINE_AK = os.environ.get("VOLCENGINE_AK", self.VOLCENGINE_AK)
        self.VOLCENGINE_SK = os.environ.get("VOLCENGINE_SK", self.VOLCENGINE_SK)

        # OSS 配置
        self.OSS_ENABLED = os.environ.get("OSS_ENABLED", "false").lower() == "true"
        self.OSS_ENDPOINT = os.environ.get("OSS_ENDPOINT", self.OSS_ENDPOINT)
        self.OSS_ACCESS_KEY_ID = os.environ.get("OSS_ACCESS_KEY_ID", self.OSS_ACCESS_KEY_ID)
        self.OSS_ACCESS_KEY_SECRET = os.environ.get(
            "OSS_ACCESS_KEY_SECRET", self.OSS_ACCESS_KEY_SECRET
        )

        # OpenAI 配置
        self.OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", self.OPENAI_API_KEY)
        self.OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", self.OPENAI_BASE_URL)
        self.OPENAI_MODEL = os.environ.get("OPENAI_MODEL", self.OPENAI_MODEL)

        # 火山方舟 / Seedance 配置
        self.ARK_API_KEY = os.environ.get("ARK_API_KEY", self.ARK_API_KEY)
        self.ARK_BASE_URL = os.environ.get("ARK_BASE_URL", self.ARK_BASE_URL)
        self.SEEDANCE_OMNI_MODEL = os.environ.get(
            "SEEDANCE_OMNI_MODEL", self.SEEDANCE_OMNI_MODEL
        )
        self.SEEDANCE_OMNI_CREATE_PATH = os.environ.get(
            "SEEDANCE_OMNI_CREATE_PATH", self.SEEDANCE_OMNI_CREATE_PATH
        )
        self.SEEDANCE_OMNI_QUERY_PATH = os.environ.get(
            "SEEDANCE_OMNI_QUERY_PATH", self.SEEDANCE_OMNI_QUERY_PATH
        )
        self.SEEDANCE_OMNI_LIST_PATH = os.environ.get(
            "SEEDANCE_OMNI_LIST_PATH", self.SEEDANCE_OMNI_LIST_PATH
        )
        self.SEEDANCE_OMNI_CANCEL_PATH = os.environ.get(
            "SEEDANCE_OMNI_CANCEL_PATH", self.SEEDANCE_OMNI_CANCEL_PATH
        )

        # 火山方舟国际版 / Seedance 国际版配置
        self.ARK_INTL_API_KEY = os.environ.get("ARK_INTL_API_KEY", self.ARK_INTL_API_KEY)
        self.ARK_INTL_BASE_URL = os.environ.get("ARK_INTL_BASE_URL", self.ARK_INTL_BASE_URL)
        self.SEEDANCE_INTL_MODEL = os.environ.get("SEEDANCE_INTL_MODEL", self.SEEDANCE_INTL_MODEL)

        # 视频画质增强配置
        self.VIDEO_ENHANCE_API_KEY = os.environ.get(
            "VIDEO_ENHANCE_API_KEY", self.VIDEO_ENHANCE_API_KEY
        )
        self.VIDEO_ENHANCE_BASE_URL = os.environ.get(
            "VIDEO_ENHANCE_BASE_URL", self.VIDEO_ENHANCE_BASE_URL
        )
        self.VIDEO_ENHANCE_CREATE_PATH = os.environ.get(
            "VIDEO_ENHANCE_CREATE_PATH", self.VIDEO_ENHANCE_CREATE_PATH
        )
        self.VIDEO_ENHANCE_QUERY_PATH = os.environ.get(
            "VIDEO_ENHANCE_QUERY_PATH", self.VIDEO_ENHANCE_QUERY_PATH
        )

        # 日志配置
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", self.LOG_LEVEL)

        # 视觉服务配置
        self.VISUAL_API_REGION = os.environ.get("VISUAL_API_REGION", self.VISUAL_API_REGION)

        # 确保目录存在
        self._ensure_directories()

    def _ensure_directories(self):
        """确保必要的目录存在"""
        for folder in [self.UPLOAD_FOLDER, self.OUTPUT_FOLDER]:
            Path(folder).mkdir(parents=True, exist_ok=True)

    def is_mysql_enabled(self) -> bool:
        """检查是否启用 MySQL"""
        return self.DB_TYPE == "mysql"

    def is_oss_enabled(self) -> bool:
        """检查是否启用 OSS"""
        return self.OSS_ENABLED and bool(self.OSS_ACCESS_KEY_ID and self.OSS_ACCESS_KEY_SECRET)

    def is_openai_configured(self) -> bool:
        """检查是否配置了 OpenAI"""
        return bool(self.OPENAI_API_KEY)

    def is_volcengine_configured(self) -> bool:
        """检查是否配置了火山引擎"""
        return bool(self.VOLCENGINE_AK and self.VOLCENGINE_SK)

    def is_seedance_omni_configured(self) -> bool:
        """检查是否配置了 Seedance 2.0 全能视频接口。"""
        return bool(self.ARK_API_KEY and self.ARK_BASE_URL and self.SEEDANCE_OMNI_MODEL)

    def is_seedance_intl_configured(self) -> bool:
        """检查是否配置了 Seedance 2.0 国际版全能视频接口。"""
        return bool(self.ARK_INTL_API_KEY and self.ARK_INTL_BASE_URL and self.SEEDANCE_INTL_MODEL)

    def is_video_enhance_configured(self) -> bool:
        """检查是否配置了视频画质增强接口。"""
        return bool(self.VIDEO_ENHANCE_API_KEY and self.VIDEO_ENHANCE_BASE_URL)


# 全局配置实例
config = Config()
