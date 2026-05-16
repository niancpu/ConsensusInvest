type Props = {
  failureSummary: string;
  hasWorkflow: boolean;
  hasTraceNodes: boolean;
  isWorkflowFailed: boolean;
  visibleFailureMessage: string;
};

export default function TraceInspectorEmptyState({
  failureSummary,
  hasWorkflow,
  hasTraceNodes,
  isWorkflowFailed,
  visibleFailureMessage,
}: Props) {
  return (
    <div className="description-list">
      <article className="description-item">
        <h3>
          {hasTraceNodes
            ? '选择节点'
            : isWorkflowFailed
              ? 'workflow 失败'
              : hasWorkflow
                ? 'Trace 未就绪'
                : '创建 workflow'}
        </h3>
        <p>
          {hasTraceNodes
            ? '点击判断、Round Summary、Agent Argument、Evidence 或 Raw Item 节点查看下钻详情。'
            : isWorkflowFailed
              ? visibleFailureMessage || failureSummary || '任务失败且没有生成可审计判断链；需要先处理失败原因，再重新运行 workflow。'
              : hasWorkflow
                ? '等待 trace_nodes 返回后可从判断溯源图进入节点详情；当前不会用实体关系或演示数据占位。'
                : '先创建分析任务，页面会订阅 SSE 事件并在 trace 可用后展示真实推理链路。'}
        </p>
      </article>
    </div>
  );
}
