# Entity API

本文档定义实体、实体关联 Evidence 和实体关系。

## 12. Entities And Relations

### 12.1 查询实体列表

```http
GET /api/v1/entities?query=银行&type=industry&limit=20&offset=0
```

响应：

```json
{
  "data": [
    {
      "entity_id": "ent_industry_bank",
      "entity_type": "industry",
      "name": "银行",
      "aliases": ["银行业"],
      "description": "A 股银行行业实体"
    }
  ],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 1,
    "has_more": false
  },
  "meta": {
    "request_id": "req_20260513_100700"
  }
}
```

### 12.2 查询实体详情

```http
GET /api/v1/entities/{entity_id}
```

响应同单条 Entity。

### 12.3 查询实体关联 Evidence

```http
GET /api/v1/entities/{entity_id}/evidence?limit=50&offset=0
```

响应为 Evidence 列表。

### 12.4 查询实体关系

```http
GET /api/v1/entities/{entity_id}/relations?depth=1
```

响应：

```json
{
  "data": [
    {
      "relation_id": "erel_000001_bank_001",
      "from_entity_id": "ent_company_000001",
      "to_entity_id": "ent_industry_bank",
      "relation_type": "belongs_to_industry",
      "weight": 1.0,
      "evidence_ids": ["ev_20260513_000001_tushare_001"]
    }
  ],
  "meta": {
    "request_id": "req_20260513_100710"
  }
}
```

前端注解：

- Entity Relations 是跨 workflow 共享的实体语义关系。
- 不要把它和 `evidence_references` 混用。前者回答“实体之间有什么关系”，后者回答“推理链路引用了哪些证据”。

