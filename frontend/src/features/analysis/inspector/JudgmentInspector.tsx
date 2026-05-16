import { formatScore } from '../utils/format';
import type { Judgment } from '../../../types/workflow';

export default function JudgmentInspector({ judgment }: { judgment: Judgment }) {
  const signal = finalSignalLabel(judgment.final_signal);
  const horizon = timeHorizonLabel(judgment.time_horizon);
  const reasoning = readableText(judgment.reasoning) || judgmentSummary(judgment, signal);
  const riskNotes = judgment.risk_notes.map(readableText).filter((note): note is string => Boolean(note));

  return (
    <div className="description-list">
      <article className="description-item">
        <h3>{signal}</h3>
        <p>{reasoning}</p>
      </article>
      <article className="description-item">
        <h3>置信度</h3>
        <p>{formatScore(judgment.confidence)} / {horizon}</p>
      </article>
      {riskNotes.map((note) => (
        <article className="description-item" key={note}>
          <h3>风险</h3>
          <p>{note}</p>
        </article>
      ))}
    </div>
  );
}

function finalSignalLabel(value: string): string {
  const labels: Record<string, string> = {
    bullish: '偏多',
    neutral: '中性',
    bearish: '偏空',
    insufficient_evidence: '证据不足',
  };
  return labels[value] ?? (value || '-');
}

function timeHorizonLabel(value: string): string {
  const cleaned = readableText(value);
  const labels: Record<string, string> = {
    short_term: '短期',
    mid_term: '中期',
    long_term: '长期',
    short_to_mid_term: '短中期',
  };
  return cleaned ? labels[cleaned] ?? cleaned : '短中期';
}

function judgmentSummary(judgment: Judgment, signal: string): string {
  const positiveIds = judgment.key_positive_evidence_ids.join('、') || '暂无明确正向证据';
  const negativeIds = judgment.key_negative_evidence_ids.join('、') || '暂无明确负向证据';
  const argumentIds = judgment.referenced_agent_argument_ids.join('、') || '暂无明确论证';
  return `最终判断为${signal}，置信度 ${formatScore(judgment.confidence)}。判断引用代理论证 ${argumentIds}，关键正向证据 ${positiveIds}，关键负向证据 ${negativeIds}。`;
}

function readableText(value?: string | null): string {
  if (typeof value !== 'string') {
    return '';
  }
  const text = value.trim();
  if (!text || looksMojibake(text) || isGenericJudgmentReasoning(text)) {
    return '';
  }
  return text;
}

function isGenericJudgmentReasoning(value: string): boolean {
  return [
    '基于已保存智能体论证和关键证据形成判断',
    '基于已保存轮次摘要、智能体论证和关键证据',
  ].some((phrase) => value.includes(phrase));
}

function looksMojibake(value: string): boolean {
  return /[\u0000-\u001f\u007f-\u009f\ufffd\u25a1ÃÂâ]|[äåæçéè][\u0080-\u00ff]/.test(value);
}
