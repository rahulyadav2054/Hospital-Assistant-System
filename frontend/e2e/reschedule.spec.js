// End-to-end tests (PDF Member 3, Step 11). Run from frontend/:  npm run test:e2e
import { expect, test } from "@playwright/test";

async function login(page, username) {
  await page.goto("/login");
  await page.fill("#username", username);
  await page.fill("#password", "demo123");
  await page.click("button[type=submit]");
  await expect(page.getByTestId("chat-input")).toBeVisible();
}

async function ask(page, question) {
  await page.fill("[data-testid=chat-input]", question);
  await page.click("[data-testid=send]");
}

test("patient reschedules cardiology appointment", async ({ page }) => {
  await login(page, "asha");
  const cardiology = page.getByTestId("appt-APT-1042");
  await expect(cardiology).toBeVisible();
  const before = await cardiology.textContent();

  await ask(page, "Reschedule my cardiology appointment");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Cardiology");
  await dialog.getByRole("button", { name: "Confirm" }).click();

  await expect(page.getByTestId("system-message").last()).toContainText("rescheduled to");
  await expect(cardiology).not.toHaveText(before);
});

test("cancelling a reschedule changes nothing", async ({ page }) => {
  await login(page, "meera");
  const endo = page.getByTestId("appt-APT-3001");
  await expect(endo).toBeVisible();
  const before = await endo.textContent();
  await ask(page, "Please reschedule my endocrinology appointment");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByTestId("system-message").last()).toContainText("not changed");
  await expect(endo).toHaveText(before);
});

test("answers show citations and the source drawer", async ({ page }) => {
  await login(page, "asha");
  await ask(page, "What are visiting hours for ICU patients?");
  const chip = page.getByTestId("citation-chip").first();
  await expect(chip).toContainText("Visitor Policy");
  await chip.click();
  await expect(page.getByRole("dialog", { name: "Source" })).toContainText("11:00");
});

test("lab result card, emergency banner and not-found states", async ({ page }) => {
  await login(page, "meera");
  await ask(page, "What is my latest blood sugar reading?");
  await expect(page.getByTestId("lab-card").last()).toContainText("112");

  await ask(page, "I have severe chest pain right now");
  await expect(page.getByTestId("emergency-banner")).toContainText("108");

  await ask(page, "Do you have treatment information for proton beam therapy?");
  await expect(page.getByTestId("not-found").last()).toBeVisible();
});

test("surgery readiness agent: live steps, one approval, sidebar shows bookings", async ({ page }) => {
  await login(page, "rahul");
  await ask(page, "Get me ready for my surgery");
  const card = page.getByTestId("agent-card").last();
  await expect(card).toContainText("Surgery Readiness Agent");
  await expect(card.getByTestId("agent-step-1")).toContainText("Laparoscopic Cholecystectomy");
  const plan = card.getByTestId("plan-approval");
  await expect(plan).toContainText("Book Electrocardiogram (ECG)");
  await expect(plan).toContainText("Submit prior authorization");
  await plan.getByRole("button", { name: "Approve all" }).click();
  await expect(card.getByTestId("plan-done")).toContainText("PAR-");
  await expect(page.getByTestId("test-ORD-503")).toContainText("Booked");
  await expect(page.getByTestId("test-ORD-504")).toContainText("Booked");
});

test("proactive bell: notifications appear and one click starts the right agent", async ({ page }) => {
  // meera: out-of-range results (rahul's items are already handled by the surgery-readiness test above)
  await login(page, "meera");
  await expect(page.getByTestId("bell-count")).toBeVisible();
  await page.getByTestId("bell").click();
  const panel = page.getByTestId("bell-panel");
  await expect(panel).toContainText("Fasting Glucose");
  await panel.getByRole("button", { name: /Next steps/ }).first().click();
  const card = page.getByTestId("agent-card").last();
  await expect(card).toContainText("Lab Follow-up Agent");
  await expect(card).toContainText("take this report");
});

test("agent hub: Visit Planner tile builds a timeline", async ({ page }) => {
  await login(page, "meera");
  await page.getByTestId("agent-tile-visit_planner").click();
  const card = page.getByTestId("agent-card").last();
  await expect(card).toContainText("Visit Planner Agent");
  await expect(card.getByTestId("visit-timeline")).toContainText("Endocrinology");
});

test("appointment booking agent books a new appointment", async ({ page }) => {
  await login(page, "asha");
  await ask(page, "I have thyroid problems, book me a doctor");
  const card = page.getByTestId("agent-card").last();
  await expect(card).toContainText("Appointment Booking Agent");
  await card.getByRole("button", { name: "Approve booking" }).click();
  await expect(card.getByTestId("plan-done")).toContainText("Endocrinology");
  await expect(page.getByTestId("sidebar-appointments")).toContainText("Endocrinology");
});

test("wrong password shows an error", async ({ page }) => {
  await page.goto("/login");
  await page.fill("#username", "asha");
  await page.fill("#password", "nope");
  await page.click("button[type=submit]");
  await expect(page.getByRole("alert")).toContainText("Invalid");
});
