# SparkMemo
Spark 触发（阈值触发）+ Memo 备忘录，寓意达到阈值即刻弹出备忘提醒

## 目录结构

```
SparkMemo/
├── backend/                # FastAPI 后端
│   ├── app/
│   │   ├── main.py         # 入口
│   │   ├── config.py       # 配置
│   │   ├── database.py     # 数据库连接
│   │   ├── models.py       # ORM 模型
│   │   ├── schemas.py      # Pydantic 模式
│   │   ├── deps.py         # 依赖项
│   │   ├── ws_manager.py   # WebSocket 管理
│   │   ├── crud/           # 数据库操作
│   │   ├── api/            # 路由
│   │   └── services/       # 业务服务（APScheduler）
│   ├── static/             # Vite 构建产物（运行 build 后生成）
│   ├── requirements.txt
│   └── .env.example
├── frontend/               # Vue 3 + Vite 前端
│   ├── public/
│   ├── src/
│   │   ├── api/            # axios 封装
│   │   ├── components/     # 组件
│   │   ├── views/          # 页面
│   │   ├── stores/         # Pinia
│   │   ├── router/         # 路由
│   │   ├── App.vue
│   │   └── main.js
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── start.bat / start.sh    # 启动脚本
└── .gitignore
```

## 开发启动

```bash
# 后端
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env            # 修改 DATABASE_URL
uvicorn app.main:app --reload

# 前端
cd frontend
npm install
npm run dev
```

## 生产部署

```bash
cd frontend && npm run build    # 产物输出到 ../backend/static
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
