# 生产级数字货币交易所对比分析工具

这是一个高性能、可扩展、功能丰富的生产级数字货币分析工具。它集成了多个数据源（中心化交易所、去中心化交易所、跨链桥），提供全面的交易所对比功能，包括实时行情、K线图、市场深度、套利机会发现、费用分析和定性评估。

## 核心功能

- **多维度交易所对比**:
  - **实时行情**: 通过 WebSocket 实时获取多个交易所的行情数据。
  - **历史K线图 (带缓存)**: 获取并展示历史K线图。首次获取的数据会 **自动缓存** 到本地 `data/` 目录下的 CSV 文件中，加速后续加载。
  - **市场深度**: 动态、交互式地展示所选交易对的市场深度图。
  - **综合套利分析**: 一个为套利者设计的高级视图，结合了价格、费用和 **订单簿流动性**，以提供更真实的盈利能力图景。
  - **费用分析**: 对比不同交易所、不同资产的 **充值 (Deposit)** 和 **提现 (Withdrawal)** 网络及手续费。
  - **定性数据对比**: 一个可同时比较多个交易所定性数据的表格视图，信息库 (`config/qualitative_data.yml`) 手动维护，包含安全、客服、费率等多维度信息。
- **数据持久化**:
  - **历史K线缓存**: 将下载的K线数据保存为CSV文件，避免重复请求。
  - **实时数据存储**: (可选) 使用 **SQLite** 进行轻量级、无服务器的数据持久化，存储实时行情数据以供历史分析。
- **现代化Web界面**:
  - 基于 `Streamlit` 构建，通过清晰的标签页展示不同功能模块。
- **容器化部署**:
  - 提供 `Dockerfile` 和 `docker-compose.yml`，一键启动整个应用。

## 技术架构与原理

项目采用模块化的 `src` 布局，将业务逻辑、UI和数据提供者清晰分离，易于维护和扩展。数据库已从PostgreSQL迁移到SQLite，大大简化了部署和本地设置。

### 文件结构

```
.
├── src/                    # 应用源代码
│   ├── app.py              # Streamlit 应用主入口
│   ├── config_loader.py    # 配置加载逻辑
│   ├── db.py               # 数据库管理器 (SQLite)
│   ├── engine.py           # 套利引擎
│   └── ...
├── config/                 # 配置文件
│   ├── fees.yml
│   └── qualitative_data.yml
├── data/                   # 本地数据缓存目录 (包括SQLite数据库文件)
├── tests/                  # 测试套件
├── .env                    # 环境变量文件 (本地创建)
├── requirements.txt        # Python 依赖
├── Dockerfile
└── docker-compose.yml      # 简化的单服务Docker配置
```

---

## 运行指南

### 方案一：在本地 Python 环境中运行 (推荐用于开发)

1.  **克隆项目**
    ```bash
    git clone <your-repo-url>
    cd <project-directory>
    ```

2.  **设置 Python 环境**
    -   建议使用 Python 3.9+。
    -   创建并激活一个虚拟环境：
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        # On Windows, use: venv\Scripts\activate
        ```

3.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

4.  **创建环境变量文件 (`.env`)**
    -   在项目根目录下创建一个名为 `.env` 的文件。
    -   (可选) 您可以在此文件中设置 `SQLITE_DB_PATH` 来指定数据库文件的位置，默认值为 `data/crypto_data.db`。您也可以设置API密钥。

5.  **启动应用**
    -   **重要**: 请务必使用 `streamlit run` 命令来启动应用。直接使用 `python src/app.py` 将无法正常工作并会导致 `Missing ScriptRunContext` 警告。
    -   在项目根目录下运行以下命令：
        ```bash
        streamlit run src/app.py
        ```
    -   应用将在您的浏览器中打开。

### 方案二：通过 Docker 运行

1.  **准备环境**: 确保已安装 [Docker](https://www.docker.com/products/docker-desktop/) 和 [Docker Compose](https://docs.docker.com/compose/install/)。

2.  **启动服务**:
    -   此命令将构建镜像并以后台模式启动应用。
        ```bash
        docker compose up --build -d
        ```
    -   数据库文件将自动在 `data/` 目录下创建，并通过卷挂载持久化。

3.  **访问应用**: 打开浏览器，访问 `http://localhost:8501`。

---

## 如何运行测试

测试套件用于验证核心业务逻辑（如套利引擎）的正确性。

1.  **安装测试依赖**
    ```bash
    pip install -r requirements.txt
    ```
2.  **运行测试**
    -   在项目根目录下，运行以下命令以确保 `src` 目录在Python的路径中：
    ```bash
    PYTHONPATH=. pytest
    ```
