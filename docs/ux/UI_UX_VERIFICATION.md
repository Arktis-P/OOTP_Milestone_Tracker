# UI/UX Verification Evidence

- Date: 2026-07-24
- Mode: QT_QPA_PLATFORM=offscreen
- MainWindow path: MainWindow instantiated (ko); MainWindow instantiated (en)

| Screen | File | Requested size | Image size | Non-empty | Checks | Status | Note |
|---|---:|---:|---:|---:|---|---|---|
| dashboard | dashboard.png | 1650x900 | 1650x900 | yes | dashboard workflow panel and next actions | captured |  |
| milestone_basic | milestone_basic.png | 1650x900 | 1650x900 | yes | basic filters, readable record table | captured |  |
| import_center | import_center.png | 1650x900 | 1650x900 | yes | three import cards and five-step flow | captured |  |
| manual_record_basic | manual_record_basic.png | 1650x900 | 1650x900 | yes | manual one-record default entry page | captured |  |
| streak_page | streak_page.png | 1650x900 | 1650x900 | yes | active/recent streak page with filters | captured |  |
| settings | settings.png | 1650x900 | 1650x900 | yes | normal settings separated from advanced tools | captured |  |
| advanced_tools | advanced_tools.png | 1650x900 | 1650x900 | yes | maintenance and danger zone separation | captured |  |
| milestone_1366x768 | milestone_1366x768.png | 1366x768 | 1366x768 | yes | milestone page at 1366x768 | captured |  |
| minimum_1000x680 | minimum_1000x680.png | 1000x680 | 1000x680 | yes | minimum window accessibility | captured |  |
| milestone_advanced_filter | milestone_advanced_filter.png | 1650x900 | 1650x900 | yes | advanced filters expanded | captured |  |
| milestone_detail | milestone_detail.png | 1650x900 | 1650x900 | yes | selected record detail panel | captured |  |
| message_review | message_review.png | 1650x900 | 1650x900 | yes | parsed message list, original text, extracted result, approval actions | captured |  |
| dashboard_en | en/dashboard.png | 1650x900 | 1650x900 | yes | English dashboard layout and clipping | captured |  |
| milestone_1366x768_en | en/milestone_1366x768.png | 1366x768 | 1366x768 | yes | English milestone page at 1366x768 | captured |  |
| import_center_en | en/import_center.png | 1650x900 | 1650x900 | yes | English import center layout and clipping | captured |  |
| message_review_en | en/message_review.png | 1650x900 | 1650x900 | yes | English message review layout and clipping | captured |  |

## Verification notes

- The script validates each PNG by checking the captured pixmap dimensions and saved file size.
- Captures in `docs/ux/screenshots/final/` prove that each screen instantiated, rendered at the requested pixel size, exposed its expected widgets, and raised no exception.
- These offscreen captures do not prove that text is unclipped or controls are usable at Windows 125% DPI.
- Translation completeness is covered by the automated localization tests; the screenshot pass does not replace those tests.
- English captures in `docs/ux/screenshots/final/en/` provide the same structural evidence. This runner reports an empty Qt font database, so glyph readability in both languages still requires a normal Windows desktop check.
- Screens marked `failed` indicate the current branch could not instantiate that view in the offscreen environment; the exception is preserved in the table.
