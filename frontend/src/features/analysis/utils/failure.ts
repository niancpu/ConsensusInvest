export function summarizeFailurePayload(payload: Record<string, unknown>): string {
  const code = typeof payload.code === 'string' ? payload.code : '';
  const message = typeof payload.message === 'string' ? payload.message : '';
  const gaps = Array.isArray(payload.gaps) ? payload.gaps : [];
  const gapDescriptions = gaps
    .map((gap) => {
      if (!gap || typeof gap !== 'object') {
        return '';
      }
      const value = gap as Record<string, unknown>;
      return typeof value.description === 'string' ? value.description : '';
    })
    .filter(Boolean);

  if (code === 'insufficient_evidence') {
    return gapDescriptions.length > 0
      ? `证据不足：${gapDescriptions.join('；')}`
      : '证据不足，Judge 没有形成最终判断。';
  }
  if (code === 'agent_swarm_failed') {
    return message ? `Agent 论证失败：${message}` : 'Agent 论证失败，未生成最终判断。';
  }
  if (code === 'judge_failed') {
    return message ? `Judge 汇总失败：${message}` : 'Judge 汇总失败，未生成最终判断。';
  }
  if (code === 'evidence_acquisition_failed') {
    return message ? `证据采集失败：${message}` : '证据采集失败，未找到可用于分析的 Evidence。';
  }
  if (code === 'missing_runtime_configuration') {
    return message || '分析无法开始：后端运行配置不完整，请先配置数据源或模型 key。';
  }
  return [friendlyFailureCode(code), message].filter(Boolean).join('：') || '';
}

export function friendlyFailureCode(code: string): string {
  const labels: Record<string, string> = {
    missing_judgment: '最终判断缺失',
  };
  return labels[code] ?? code;
}
