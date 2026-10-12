# 贡献指南

感谢你对 Social Sense 项目的关注！以下是参与贡献的指南。

## 开发流程

1. **Fork 本仓库**到你的 GitHub 账号
2. **克隆**你 Fork 的仓库到本地
3. **创建新分支**：`git checkout -b feature/你的功能名`
4. **编写代码**并测试
5. **提交代码**：`git commit -m "feat: 添加了xxx功能"`
6. **推送分支**：`git push origin feature/你的功能名`
7. **创建 Pull Request**

## 提交规范

请使用以下格式编写 commit message：

```
<类型>: <描述>

[可选的详细说明]
```

### 类型说明

| 类型 | 说明 |
|------|------|
| feat | 新功能 |
| fix | 修复 bug |
| docs | 文档变更 |
| style | 代码格式（不影响功能） |
| refactor | 重构（不是新功能也不是修 bug） |
| test | 添加测试 |
| chore | 构建或辅助工具变更 |

### 示例

```
feat: 添加微博数据采集功能
fix: 修复登录token过期未跳转的问题
docs: 更新API文档
```

## 代码规范

### Python 后端

- 遵循 PEP 8 编码规范
- 函数和类使用中文或英文 docstring
- 变量和函数名使用 snake_case
- 类名使用 PascalCase

### JavaScript 前端

- 使用 ESLint 进行代码检查
- 组件名使用 PascalCase
- 变量和函数名使用 camelCase
- 使用函数式组件和 Hooks

## 分支管理

- `main`：主分支，保持稳定
- `develop`：开发分支
- `feature/*`：功能分支
- `fix/*`：修复分支

## 问题反馈

如果发现 bug 或有功能建议，请通过 GitHub Issues 提交。
