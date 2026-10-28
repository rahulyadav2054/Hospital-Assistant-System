# Evaluation report

Mode: **offline** - 40 cases - answered by: offline 40

| Metric | Result | Target | |
|---|---|---|---|
| Intent accuracy | 100% (40 cases) | 90% | PASS |
| Answer contains expected facts | 100% (35 cases) | 90% | PASS |
| Correct citation present | 100% (35 cases) | 95% | PASS |
| Not-found precision | 100% (5 cases) | 100% | PASS |
| Median latency | 233 ms | < 6000 ms | PASS |

## Cases

| # | User | Question | Mode | Intent | Status | Intent ok | Facts ok | Cited | Not-found ok |
|---|---|---|---|---|---|---|---|---|---|
| 1 | asha | What are ICU visiting hours? | offline | policy | ok | yes | yes | yes | - |
| 2 | asha | Can children visit the ICU? | offline | policy | ok | yes | yes | yes | - |
| 3 | rahul | How many visitors can stay overnight in a general ward? | offline | policy | ok | yes | yes | yes | - |
| 4 | meera | Who can see my medical records? | offline | policy | ok | yes | yes | yes | - |
| 5 | asha | What is the no-show policy? | offline | policy | ok | yes | yes | yes | - |
| 6 | asha | How do I schedule an MRI scan? | offline | procedure | ok | yes | yes | yes | - |
| 7 | asha | How do I book a CT scan with contrast? | offline | procedure | ok | yes | yes | yes | - |
| 8 | meera | How do I prepare for an MRI? | offline | procedure | ok | yes | yes | yes | - |
| 9 | rahul | How can I get a copy of my medical records? | offline | procedure | ok | yes | yes | yes | - |
| 10 | meera | How long do lab reports take? | offline | policy | ok | yes | yes | yes | - |
| 11 | asha | What are my upcoming appointments? | offline | personal_data | ok | yes | yes | yes | - |
| 12 | meera | When is my next appointment? | offline | personal_data | ok | yes | yes | yes | - |
| 13 | rahul | Do I have an appointment with the surgeon? | offline | personal_data | ok | yes | yes | yes | - |
| 14 | asha | Show my past appointments | offline | personal_data | ok | yes | yes | yes | - |
| 15 | john | What are my upcoming appointments? | offline | personal_data | ok | yes | yes | yes | - |
| 16 | asha | Am I covered for knee replacement under my insurance plan? | offline | eligibility | ok | yes | yes | yes | - |
| 17 | john | Am I covered for knee replacement? | offline | eligibility | ok | yes | yes | yes | - |
| 18 | meera | Is cosmetic surgery covered? | offline | eligibility | ok | yes | yes | yes | - |
| 19 | rahul | Is gallbladder surgery covered? | offline | eligibility | ok | yes | yes | yes | - |
| 20 | meera | Will my insurance cover a knee replacement? | offline | eligibility | ok | yes | yes | yes | - |
| 21 | meera | What is my latest blood sugar reading? | offline | lab_result | ok | yes | yes | yes | - |
| 22 | meera | Show my HbA1c trend | offline | lab_result | ok | yes | yes | yes | - |
| 23 | rahul | What were my CBC results? | offline | lab_result | ok | yes | yes | yes | - |
| 24 | asha | What is my cholesterol level? | offline | lab_result | ok | yes | yes | yes | - |
| 25 | meera | What was my latest creatinine? | offline | lab_result | ok | yes | yes | yes | - |
| 26 | rahul | My doctor recommended surgery. What pre-operative tests are still pending? | offline | multi_step | ok | yes | yes | yes | - |
| 27 | rahul | Which pre-op tests do I still need before my operation? | offline | multi_step | ok | yes | yes | yes | - |
| 28 | rahul | What tests are pending before my surgery? | offline | multi_step | ok | yes | yes | yes | - |
| 29 | asha | What pre-op tests are pending for my knee surgery? | offline | multi_step | ok | yes | yes | yes | - |
| 30 | rahul | Have I completed my pre-operative tests? | offline | multi_step | ok | yes | yes | yes | - |
| 31 | asha | Reschedule my cardiology appointment | offline | action | ok | yes | yes | yes | - |
| 32 | meera | Please reschedule my endocrinology appointment | offline | action | ok | yes | yes | yes | - |
| 33 | rahul | Can you move my surgery consultation to another day? | offline | action | ok | yes | yes | yes | - |
| 34 | asha | Reschedule my appointment tomorrow | offline | action | ok | yes | yes | yes | - |
| 35 | john | Reschedule my orthopedics appointment to next week | offline | action | ok | yes | yes | yes | - |
| 36 | asha | Do you have treatment information for proton beam therapy? | offline | policy | not_found | yes | - | - | yes |
| 37 | asha | Do you have a helipad? | offline | policy | not_found | yes | - | - | yes |
| 38 | meera | What vaccines are needed for travel to Brazil? | offline | policy | not_found | yes | - | - | yes |
| 39 | rahul | Can I bring my dog to the ward? | offline | policy | not_found | yes | - | - | yes |
| 40 | asha | Tell me a joke | offline | out_of_scope | not_found | yes | - | - | yes |
