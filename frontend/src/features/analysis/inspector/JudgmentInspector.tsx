import { formatScore } from '../utils/format';
import type { Judgment } from '../../../types/workflow';

export default function JudgmentInspector({ judgment }: { judgment: Judgment }) {
  return (
    <div className="description-list">
      <article className="description-item">
        <h3>{judgment.final_signal}</h3>
        <p>{judgment.reasoning}</p>
      </article>
      <article className="description-item">
        <h3>置信度</h3>
        <p>{formatScore(judgment.confidence)} / {judgment.time_horizon}</p>
      </article>
      {judgment.risk_notes.map((note) => (
        <article className="description-item" key={note}>
          <h3>风险</h3>
          <p>{note}</p>
        </article>
      ))}
    </div>
  );
}
