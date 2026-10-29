// The AI agents shown in the UI. Names match ai/agents/*.py (NAME).
export const AGENTS = [
  { name: "surgery_readiness", icon: "🩺", title: "Surgery Readiness",
    desc: "Checks insurance, required tests and paperwork for your surgery, then books what is missing." },
  { name: "appointment_booking", icon: "📅", title: "Appointment Booking",
    desc: "Finds the right department and doctor and books a slot that fits your preferences." },
  { name: "visit_planner", icon: "🗺️", title: "Visit Planner",
    desc: "Builds your hospital-day timeline: where to go, what to bring, what to prepare." },
  { name: "proactive_care", icon: "🔔", title: "Proactive Care",
    desc: "Watches your record and tells you what needs attention - before you ask." },
  { name: "lab_follow_up", icon: "🧪", title: "Lab Follow-up",
    desc: "Turns an out-of-range result into the right follow-up, without guessing what it means." },
  { name: "cost_estimate", icon: "💰", title: "Cost Estimate",
    desc: "Estimates your share of a procedure and prepares the insurer pre-approval." },
  { name: "smart_reschedule", icon: "🔁", title: "Smart Rescheduling",
    desc: "Moves every affected appointment around your travel or time preferences - one approval." },
];

export const AGENT_BY_NAME = Object.fromEntries(AGENTS.map((a) => [a.name, a]));

// One example request per agent and demo patient, chosen so each one works with that patient's data.
const EXAMPLES = {
  asha: {
    surgery_readiness: "Get me ready for my surgery",
    appointment_booking: "I have thyroid problems, book me a doctor next week in the afternoon",
    visit_planner: "Plan my visit tomorrow",
    proactive_care: "Check my reminders",
    lab_follow_up: "My cholesterol report is high, what should I do next?",
    cost_estimate: "How much will my knee replacement cost?",
    smart_reschedule: "I'm travelling next week, move my appointments",
  },
  rahul: {
    surgery_readiness: "Get me ready for my surgery",
    appointment_booking: "I have fever, book me a doctor",
    visit_planner: "Plan my next visit",
    proactive_care: "Check my reminders",
    lab_follow_up: "My CBC results, what should I do next?",
    cost_estimate: "How much will my gallbladder surgery cost?",
    smart_reschedule: "Move all my appointments to afternoons",
  },
  meera: {
    surgery_readiness: "Get me ready for my surgery",
    appointment_booking: "Book an appointment with an orthopedic doctor",
    visit_planner: "Plan my next visit",
    proactive_care: "Check my reminders",
    lab_follow_up: "My sugar report is high, what should I do next?",
    cost_estimate: "How much will an MRI scan cost?",
    smart_reschedule: "Move all my appointments to afternoons",
  },
  john: {
    surgery_readiness: "Get me ready for my surgery",
    appointment_booking: "I have fever, book me a doctor",
    visit_planner: "Plan my next visit",
    proactive_care: "Check my reminders",
    lab_follow_up: "My cholesterol report is high, what next?",
    cost_estimate: "How much will knee replacement cost me?",
    smart_reschedule: "Move all my appointments to mornings",
  },
};

export function exampleFor(username, agentName) {
  return EXAMPLES[username]?.[agentName] ?? EXAMPLES.asha[agentName];
}
