"""
新的应用入口 - 使用模块化结构

这是重构后的应用入口，展示了如何使用新的模块化架构
"""
from flask import Flask, render_template, session, redirect, url_for, request
from app.config import config
from app.extensions import init_logging, init_directories, init_error_handlers
from app.utils import ApiResponse
import database


def create_app():
    """创建并配置 Flask 应用"""
    app = Flask(__name__, template_folder='templates', static_folder='static')

    # 基础配置
    app.config['SECRET_KEY'] = config.SECRET_KEY
    app.config['DEBUG'] = config.DEBUG
    app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
    from datetime import timedelta
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=config.SESSION_LIFETIME_DAYS)

    # 初始化扩展
    init_logging(app)
    init_directories(app)
    init_error_handlers(app)

    # 注册蓝图
    register_blueprints(app)

    # 注册页面路由（这些暂时保留在主文件中，后续可继续拆分）
    register_page_routes(app)

    # 注册错误处理器
    register_error_handlers(app)

    # 初始化数据库
    database.init_database()

    return app


def register_blueprints(app: Flask):
    """注册所有蓝图"""
    from app.api import (
        auth_bp, projects_bp, admin_bp, image_bp, batch_bp,
        video_bp, script_bp, storyboard_bp, tools_bp, content_bp
    )

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(image_bp)
    app.register_blueprint(batch_bp)
    app.register_blueprint(video_bp)
    app.register_blueprint(script_bp)
    app.register_blueprint(storyboard_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(content_bp)


def register_page_routes(app: Flask):
    """注册页面路由（渲染 HTML 模板的路由）"""

    # 主页
    @app.route('/')
    def index():
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))

        # 获取当前用户信息
        user_id = session.get('user_id')
        current_project_id = session.get('current_project_id')

        # 确保有当前项目
        if not current_project_id:
            projects = database.get_user_projects(user_id)
            if projects:
                current_project_id = projects[0]['id']
                database.set_user_current_project(user_id, current_project_id)
                session['current_project_id'] = current_project_id

        return render_template('index.html',
                             user={'id': user_id, 'username': session.get('username')},
                             current_project_id=current_project_id)

    # 静态资源
    @app.route('/asset/<path:filename>')
    def asset_file(filename):
        return send_from_directory('asset', filename)

    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory('static', 'favicon.ico')

    # 临时：重定向旧的路由到新的蓝图
    # 这些将在迁移完成后删除


def register_error_handlers(app: Flask):
    """注册错误处理器"""
    # 已经在 app.extensions.init_error_handlers 中处理
    pass


if __name__ == '__main__':
    # 创建应用
    app = create_app()

    # 启动服务
    app.run(host='0.0.0.0', port=5000, debug=config.DEBUG)