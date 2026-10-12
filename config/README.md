# 环境配置

在仓库根目录复制示例后编辑配置：

```bash
cp config/.env.example config/.env
```

`config/.env` 保存本机环境变量，已由根目录 `.gitignore` 忽略。后端和 Agent 均按代码文件所在位置查找它，不依赖启动时的工作目录；进程环境变量优先于文件内容。旧的根目录或模块目录 `.env` 仅作为兼容来源。

Docker Compose 配置位于 `deploy/docker-compose.yml`，在仓库根目录显式指定环境文件：

```bash
docker compose --env-file config/.env -f deploy/docker-compose.yml up -d --build
```

测试配置位于 `tests/pytest.ini`：

```bash
python -m pytest -c tests/pytest.ini
```

`.gitignore`、`.gitattributes` 和 `skills-lock.json` 是工具按约定位置读取的仓库级文件，保留在根目录。
