# 2026-09-27 · 公开 AWRP 快照边界

## 决策

不复用私有生产 relay 的 Git 历史公开发布。公开仓库只包含协议、schema、标准库参考实现、示例、测试和公开安全文档。

## 原因

原仓库根目录含 `projects/`、`channels/`、`contexts/`、`incidents/`、`tasks/` 与 `bridge/requests/`，保存真实项目名、任务目标和交付历史。直接翻转 visibility 会把这些状态一起公开。

## 公开仓库内容

- `protocol/`：协议与 worker/coordinator 合同
- `schemas/`：公开 JSON schema
- `tools/`：标准库参考 CLI 与单一写入 transport
- `examples/`：可丢弃 demo
- `tests/`：上游参考测试和公开快照边界测试
- `bridge/README.md`：transport 边界，不含真实请求
- `.github/workflows/tests.yml`：公开 CI

## 明确排除

- 所有 relay 运行状态和历史
- 本地 workspace binding / session
- 私有项目、任务、incident、artifact
- 私有仓库名或账号绑定常量
- 任何凭据、token、真实请求/响应

## 验证

`python -m unittest tests/test_public_snapshot.py -v` 和 `python -m pytest -q` 必须通过。发布前还必须运行本地 secret/privacy 扫描。
