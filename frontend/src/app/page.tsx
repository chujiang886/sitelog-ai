export default function HomePage(): JSX.Element {
  return (
    <section className="space-y-6">
      <div>
        <p className="text-sm font-medium text-boip-primary-main">项目总览</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-900">项目状态看板</h1>
        <p className="mt-2 text-slate-600">BOIP Phase 0 占位页面，业务指标将在后续阶段接入。</p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {['项目', '知识规则', 'Agent'].map((label) => (
          <article key={label} className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm text-slate-500">{label}</p>
            <p className="mt-3 text-2xl font-semibold text-slate-300">占位</p>
          </article>
        ))}
      </div>
    </section>
  );
}
