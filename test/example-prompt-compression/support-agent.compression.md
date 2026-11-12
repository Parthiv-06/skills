# Compression report: support-agent.md

## 1. Verdict

| | Original | Compressed (lossless tier) |
|---|---|---|
| Size | 2,418 chars, ~604 tokens | 978 chars, ~244 tokens |
| Saved | | **60%** (1,440 chars, ~360 tokens) |
| Signal score | | **40%**: only 40% of the original was needed |
| Static gate | | PASS: every tool name, parameter, limit, and exact string kept |
| Behavioral test | | **Not run yet.** Cases are in `tests.md`. Until they pass, treat the compressed prompt as unverified |

## 2. Quality issues (not about length)

These were in the original. The compressed prompt keeps the original behavior. Fixing them is your call.

| # | Issue | Suggested fix |
|---|---|---|
| A | VAGUE: a refund that is both older than 30 days **and** over $500. Refuse it, or escalate it? The original lists eligibility first, so the compressed prompt does too | Add: "Check the 30-day rule first; escalate only eligible refunds over $500" (or the reverse) |
| B | VAGUE: is day 30 itself inside "within 30 days"? | "placed 30 or fewer days ago" |
| C | GAP: the agent must call `lookup_order` with `order_id`, but nothing says what to do if the customer has not given one | "If you don't have the order ID, ask for it" |
| D | GAP: no tool provides `<ticket_id>`, so the agent may invent one | Say where the ticket ID comes from |

## 3. Inventory

| # | Original (short quote) | Label | What happened |
|---|---|---|---|
| 1 | "customer support assistant for ShopFast, an online store" | CORE | Kept, shorter |
| 2 | "helpful, friendly and professional… polite and courteous… at all times… make sure that you are being helpful" | DEFAULT + FILLER | Collapsed to "Be friendly, polite, and professional". Optional cut |
| 3 | "IMPORTANT: You MUST always look up the order… `lookup_order`… `order_id`" | CORE | Kept, emphasis words removed |
| 4 | "never guess order details. Never make up order information. If you don't know… look it up" | DUPLICATE of 3 | Merged: "Never guess or invent order details" |
| 5 | "When a customer asks for a refund, you should first check the order" | DUPLICATE of 3 | Merged (3 already covers any order question) |
| 6 | "Refunds… within 30 days… more than 30 days… politely explain… not eligible" | CORE / VERBOSE | Kept, shorter |
| 7 | "refunds over $500… escalated… `escalate_ticket`… "refund_over_limit"" | CORE | Kept exactly |
| 8 | "you should not process refunds over $500 yourself under any circumstances" | DUPLICATE of 7 | Merged: "Never process a refund over $500 yourself" |
| 9 | "use the `issue_refund` tool. Make sure to always confirm the amount… before" | CORE | Kept, shorter |
| 10 | "Do not issue a refund without confirming with the customer first" | DUPLICATE of 9 | Merged |
| 11 | "Think step by step… Take your time… correct and accurate" | DEFAULT | Collapsed to one sentence. Optional cut |
| 12 | "angry or upset… empathetic… Acknowledge their feelings. Stay calm and professional" | VERBOSE | Kept, one sentence |
| 13 | "never share other customers' information… privacy… personal data" | CORE (safety) | Kept, one sentence |
| 14 | "short and concise. Don't write long paragraphs. Customers prefer short answers" | VERBOSE | Kept: "Keep answers short; no long paragraphs" |
| 15 | "include the ticket ID in the format "Ticket: #<ticket_id>"… tracking system" | CORE | Kept exactly |
| 16 | "Never forget to include the ticket ID at the end of every reply" | DUPLICATE of 15 | Merged |
| 17 | "unrelated to ShopFast… politely tell them you can only help with ShopFast orders and account questions" | CORE | Kept |
| 18 | "Remember: always be helpful, always be polite… Always include the ticket ID" | DUPLICATE of 2, 3, 4, 9, 15 | Removed (every item lives elsewhere) |

## 4. Compressed prompt

See `support-agent.compressed.md`.

## 5. Ledger

Every original unit maps to the compressed prompt:

| Unit | Where it is now |
|---|---|
| 1, 2, 11, 14 | Paragraph 1 |
| 3, 4, 5 | "Orders" |
| 6, 7, 8, 9, 10 | "Refunds" (same order as the original) |
| 12 | Upset-customer paragraph |
| 13 | Privacy line |
| 17 | Off-topic line |
| 15, 16 | Last line |
| 18 | Duplicates only; nothing unique to keep |

## 6. Test results

Not run. Run `tests.md` against both prompts on the model this agent uses, with at least 3 runs per case. Any check the compressed prompt fails more often than the original means restoring that unit.

## 7. Optional cuts (tested tier)

Each one needs the behavioral test before you take it. Together they would save about 30 more tokens, bringing the prompt to ~212 tokens (35% of the original).

| Cut | Saves | Risk |
|---|---|---|
| "Think step by step and make sure your answer is accurate." | ~14 tokens | Low on current models. Could matter for multi-step refund logic |
| "Be friendly, polite, and professional." | ~9 tokens | Low: default behavior. Check tone on the angry-customer case |
| Both uses of "politely" | ~3 tokens | Low |
| "(required for tracking)" | ~5 tokens | Low. A stated reason can make a rule stick better, so test the ticket-ID check |
