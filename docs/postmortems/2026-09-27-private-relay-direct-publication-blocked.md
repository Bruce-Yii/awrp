# 2026-09-27 · 私有 relay 不能直接翻转

## 影响

如果把私有生产 relay 直接改为 public，会公开真实项目/任务/事件/incident 历史。

## 根因

协议实现与生产 relay state 共用同一 Git 历史。文件级脱敏无法修复已存在的 Git 历史。

## 修复

创建独立公开快照，只复制公开安全的协议、schema、实现、示例、测试和文档；不复制私有状态。

## 预防

`tests/test_public_snapshot.py` 固化顶层 allowlist、私有路径 denylist、凭据模式和个人/私有标识扫描。后续任何新增文件必须通过该测试。
