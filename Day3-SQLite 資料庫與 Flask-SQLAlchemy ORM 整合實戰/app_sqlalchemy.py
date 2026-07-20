import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# 配置資料庫檔案路徑
# sqlite://// 加上絕對路徑，指明將 guestbook.db 建立在當前專案目錄下
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'guestbook.db')

# 關閉不必要的追蹤修改提示，以節省記憶體開銷
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化 SQLAlchemy 實例，綁定到 Flask app
db = SQLAlchemy(app)