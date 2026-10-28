import AgentCard, { PlanApproval } from "./AgentCard.jsx";
import { CARD_MAP } from "./Cards.jsx";
import CitationChips from "./CitationChips.jsx";
import MessageBubble from "./MessageBubble.jsx";
import { EmergencyBanner, ErrorNotice, NotFoundNotice, UnauthorizedNotice } from "./Notices.jsx";

/** Renders one assistant response according to its status, intent and card types. */
export default function Reply({ r, onOpenSource, onPlanDone }) {
  if (r.intent === "agent" && r.agent) {
    return <AgentCard title={r.agent.title} steps={r.agent.steps} response={r} onOpenSource={onOpenSource}
      onPlanDone={onPlanDone} />;
  }
  if (r.status === "emergency") return <EmergencyBanner text={r.answer} />;
  if (r.status === "not_found") return <NotFoundNotice text={r.answer} />;
  if (r.status === "unauthorized") return <UnauthorizedNotice text={r.answer} />;
  if (r.status === "error") return <ErrorNotice text={r.answer} />;
  return (
    <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
      <MessageBubble text={r.answer} onCite={(id) => onOpenSource(r, id)} animate />
      {r.cards?.map((c, i) => {
        const Card = CARD_MAP[c.type];
        return Card ? <Card key={i} data={c.data} /> : null;
      })}
      {r.action_required?.type === "confirm_plan" && <PlanApproval action={r.action_required} onDone={onPlanDone} />}
      <CitationChips citations={r.citations} onOpen={(id) => onOpenSource(r, id)} />
      {r.disclaimer && <p className="text-xs text-slate-500 mt-2">ⓘ {r.disclaimer}</p>}
    </div>
  );
}
