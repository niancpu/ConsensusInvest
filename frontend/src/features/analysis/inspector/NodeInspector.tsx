import { NODE_TYPE_LABELS } from '../layout/traceConstants';
import { formatScore, truncate } from '../utils/format';
import type { SelectedNode } from './types';

export default function NodeInspector({ node }: { node: SelectedNode }) {
  return (
    <div className="description-list">
      <article className="description-item">
        <h3>{NODE_TYPE_LABELS[node.node_type]}</h3>
        <p>{node.summary || node.title || node.node_id}</p>
      </article>

      {node.node_type === 'agent_argument' && node.detail ? (
        <>
          <article className="description-item">
            <h3>代理身份</h3>
            <p>
              {node.detail.agent_id}
              {node.detail.role ? ` · ${agentRoleLabel(node.detail.role)}` : ''}
              {' · 第 '}{node.detail.round}{' 轮'}
            </p>
          </article>
          <article className="description-item">
            <h3>论证内容</h3>
            <p className="long-text">{node.detail.argument || '-'}</p>
          </article>
          <article className="description-item">
            <h3>置信度</h3>
            <p>{formatScore(node.detail.confidence)}</p>
          </article>
          <article className="description-item">
            <h3>支持证据</h3>
            <p>{node.detail.referenced_evidence_ids.join('、') || '-'}</p>
          </article>
          {node.detail.counter_evidence_ids.length > 0 ? (
            <article className="description-item">
              <h3>反驳证据</h3>
              <p>{node.detail.counter_evidence_ids.join('、')}</p>
            </article>
          ) : null}
          {node.detail.limitations.length > 0 ? (
            <article className="description-item">
              <h3>已声明局限</h3>
              <p>{node.detail.limitations.join('；')}</p>
            </article>
          ) : null}
        </>
      ) : null}

      {node.node_type === 'round_summary' && node.detail ? (
        <>
          <article className="description-item">
            <h3>轮次</h3>
            <p>第 {node.detail.round} 轮</p>
          </article>
          <article className="description-item">
            <h3>本轮摘要</h3>
            <p className="long-text">{node.detail.summary || '-'}</p>
          </article>
          <article className="description-item">
            <h3>参与代理</h3>
            <p>{node.detail.participants.join('、') || '-'}</p>
          </article>
          <article className="description-item">
            <h3>该轮论证（点击图上对应节点查看正文）</h3>
            <p>{node.detail.agent_argument_ids.join('、') || '-'}</p>
          </article>
          {node.detail.referenced_evidence_ids.length > 0 ? (
            <article className="description-item">
              <h3>引用证据</h3>
              <p>{node.detail.referenced_evidence_ids.join('、')}</p>
            </article>
          ) : null}
          {node.detail.disputed_evidence_ids.length > 0 ? (
            <article className="description-item">
              <h3>争议证据</h3>
              <p>{node.detail.disputed_evidence_ids.join('、')}</p>
            </article>
          ) : null}
        </>
      ) : null}

      {node.node_type === 'evidence' && node.detail ? (
        <>
          <article className="description-item">
            <h3>Evidence 来源</h3>
            <p>
              {node.detail.source ?? '-'}
              {node.detail.source_type ? ` · ${node.detail.source_type}` : ''}
            </p>
          </article>
          {node.detail.title ? (
            <article className="description-item">
              <h3>标题</h3>
              <p>{node.detail.title}</p>
            </article>
          ) : null}
          <article className="description-item">
            <h3>客观摘要</h3>
            <p className="long-text">{node.detail.objective_summary || node.detail.content || '-'}</p>
          </article>
          {node.detail.key_facts.length > 0 ? (
            <article className="description-item">
              <h3>结构化事实</h3>
              <KeyValueRows rows={node.detail.key_facts} />
            </article>
          ) : null}
          <article className="description-item">
            <h3>质量评分</h3>
            <p>
              来源 {formatScore(node.detail.source_quality)} / 相关性 {formatScore(node.detail.relevance)} / 结构化置信度 {formatScore(node.detail.structuring_confidence)}
            </p>
          </article>
          <article className="description-item">
            <h3>原始数据引用</h3>
            <p>{node.detail.raw_ref || '-'}</p>
          </article>
          <article className="description-item">
            <h3>原始数据来源</h3>
            {node.rawDetail ? (
              <SourceDetail raw={node.rawDetail} />
            ) : (
              <p className="long-text">
                {node.rawDetailError ||
                  '当前 Evidence 只返回了 raw_ref，未能取得对应 Raw Item；无法展示更细的数据来源。'}
              </p>
            )}
          </article>
          {node.rawDetail?.raw_payload ? (
            <article className="description-item">
              <h3>来源 Payload（节选）</h3>
              <pre className="payload-block">{truncate(JSON.stringify(node.rawDetail.raw_payload, null, 2), 720)}</pre>
            </article>
          ) : null}
        </>
      ) : null}

      {node.node_type === 'raw_item' && node.detail ? (
        <>
          <article className="description-item">
            <h3>来源</h3>
            <p>
              {node.detail.source ?? '-'}
              {node.detail.source_type ? ` · ${node.detail.source_type}` : ''}
            </p>
          </article>
          {node.detail.title ? (
            <article className="description-item">
              <h3>标题</h3>
              <p>{node.detail.title}</p>
            </article>
          ) : null}
          {node.detail.url ? (
            <article className="description-item">
              <h3>链接</h3>
              <p className="long-text">{node.detail.url}</p>
            </article>
          ) : null}
          <article className="description-item">
            <h3>原始内容</h3>
            <p className="long-text">{truncate(node.detail.content || '-', 360)}</p>
          </article>
          <article className="description-item">
            <h3>原始 Payload（节选）</h3>
            <pre className="payload-block">{truncate(JSON.stringify(node.detail.raw_payload, null, 2), 480)}</pre>
          </article>
          {node.detail.derived_evidence_ids.length > 0 ? (
            <article className="description-item">
              <h3>派生证据</h3>
              <p>{node.detail.derived_evidence_ids.join('、')}</p>
            </article>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function SourceDetail({ raw }: { raw: NonNullable<Extract<SelectedNode, { node_type: 'raw_item' }>['detail']> }) {
  const providerResponse = asRecord(raw.raw_payload.provider_response);
  const providerApi = raw.raw_payload.provider_api ?? providerResponse?.provider_api;
  const providerSymbol = raw.raw_payload.provider_symbol ?? providerResponse?.provider_symbol;
  return (
    <div className="source-detail">
      <p>
        {raw.source || '-'}
        {raw.source_type ? ` · ${raw.source_type}` : ''}
        {providerApi ? ` · ${String(providerApi)}` : ''}
        {providerSymbol ? ` · ${String(providerSymbol)}` : ''}
      </p>
      {raw.title ? <p className="long-text">{raw.title}</p> : null}
      {raw.url ? <p className="long-text">{raw.url}</p> : null}
      {raw.publish_time || raw.fetched_at ? (
        <p>
          发布时间 {raw.publish_time || '-'} / 抓取时间 {raw.fetched_at || '-'}
        </p>
      ) : null}
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function agentRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    bullish_interpreter: '多头解释',
    bearish_interpreter: '空头复核',
    neutral_reviewer: '中性复核',
    risk_reviewer: '风险复核',
  };
  return labels[role] ?? role;
}

function KeyValueRows({ rows }: { rows: Array<Record<string, unknown>> }) {
  return (
    <dl className="key-value-list">
      {rows.slice(0, 8).map((row, index) => {
        const name = row.name ?? row.metric ?? row.key ?? `fact_${index + 1}`;
        const value = row.value ?? row.text ?? row.claim ?? '-';
        const unit = row.unit ? ` ${String(row.unit)}` : '';
        const period = row.period ? `（${String(row.period)}）` : '';
        return (
          <div key={`${String(name)}-${index}`}>
            <dt>{String(name)}</dt>
            <dd>
              {String(value)}
              {unit}
              {period}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
