import GlobalNav from '../../components/GlobalNav';
import './DetailsPage.css';

function DetailsPage() {
  return (
    <main className="details-page">
      <GlobalNav className="details-nav" />

      <section className="details-layout">
        <div className="details-hero">
          <h1>多 Agent 证据链投研</h1>
          <p>
            系统把资讯报告、Evidence、Agent Argument、Round Summary 和 Judgment 分成不同状态边界。
            报告页负责读取 Report Module 视图；分析页负责创建 workflow 并展示可追踪推理链。
          </p>
          <div className="details-actions">
            <a className="primary-action" href="#analysis">开始分析</a>
            <a className="text-action" href="#reports">查看资讯报告 <span aria-hidden="true">{'->'}</span></a>
          </div>
        </div>

        <aside className="details-panel">
          <h2>页面入口</h2>
          <div>
            <strong>资讯报告</strong>
            <span>Report Module：stocks/* 与 market/* 视图</span>
          </div>
          <div>
            <strong>分析</strong>
            <span>Workflow：任务、SSE、snapshot、trace</span>
          </div>
          <div>
            <strong>历史</strong>
            <span>保留入口，等历史列表协议完成后接入</span>
          </div>
        </aside>
      </section>
    </main>
  );
}

export default DetailsPage;
