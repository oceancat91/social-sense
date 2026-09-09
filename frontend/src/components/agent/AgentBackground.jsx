/**
 * 与 Top 页面同源的冷白浅蓝背景层。
 * 仅使用 fixed 装饰层，不参与文档布局，不承载交互。
 */
export default function AgentBackground() {
  return (
    <div className="agent-atmosphere" aria-hidden="true">
      <span className="agent-atmosphere__wave agent-atmosphere__wave--far" />
      <span className="agent-atmosphere__wave agent-atmosphere__wave--mid" />
      <span className="agent-atmosphere__wave agent-atmosphere__wave--near" />
      <span className="agent-atmosphere__ambient" />
    </div>
  )
}
