type Props = {
  errorMessage: string;
  failureSummary: string;
  hasWorkflow: boolean;
  isWorkflowFailed: boolean;
  latestStage: string;
  latestStatus: string;
};

export default function TraceGraphEmptyState({
  errorMessage,
  failureSummary,
  hasWorkflow,
  isWorkflowFailed,
  latestStage,
  latestStatus,
}: Props) {
  const title = isWorkflowFailed
    ? 'workflow 已失败，未生成 trace'
    : hasWorkflow
      ? '等待 workflow trace'
      : '需要先创建 workflow';

  return (
    <div className="trace-empty-state" role="status">
      <h2>{title}</h2>
      <p>
        {errorMessage
          ? errorMessage
          : isWorkflowFailed
          ? `当前状态 ${latestStatus} / ${latestStage}。${failureSummary || '后端没有返回具体失败原因，请查看运行事件或后端日志。'}`
          : hasWorkflow
          ? `当前状态 ${latestStatus} / ${latestStage}。判断溯源图只使用后端 workflow trace 节点；trace 返回前不展示示例图。`
          : '选择股票和 workflow 配置后点击开始分析。未创建 workflow 时不展示假图或实体知识图谱。'}
      </p>
    </div>
  );
}
