# Suite 2 locked worker timeline

Times are recorded in IST (UTC+05:30). Counts refer to the phase's durable checkpoints. The first detected DSB Media interruption has no confirmed cause.

Input adapter commit: `ea38c1d2fe0ffeeec87de5eab42c58abba128c86`. The full event fields are in the [deviation log](suite2_deviations_ad7c5516.jsonl).

| Date and time (IST) | Phase | Event | Workers | Records | Free GiB |
| --- | --- | --- | ---: | ---: | ---: |
| 2026-11-21 15:07:37 | DSB Social | Started | 4 | 0 | 8.117 |
| 2026-11-21 15:21:52 | DSB Social | Completed | 4 → 0 | 2,034 | 8.349 |
| 2026-11-21 15:21:58 | DSB Media | Started | 4 | 0 | 8.481 |
| 2026-11-21 15:50:53 | DSB Media | Supervisor exit detected | 4 → 0 | 3,475 | — |
| 2026-11-21 15:53:03 | DSB Media | Detached launch exited before running jobs | — | 3,475 | — |
| 2026-11-21 15:53:11 | DSB Media | Resumed | 4 | 3,475 | 14.838 |
| 2026-11-21 15:59:49 | DSB Media | Completed | 4 → 0 | 4,068 | 14.495 |
| 2026-11-21 16:00:29 | DataHub | Started | 4 | 0 | 14.223 |
| 2026-11-21 16:50:13 | DataHub | Memory guard reduced workers | 4 → 3 | 1,140 | 4.935 |
| 2026-11-21 16:50:29 | DataHub | Resumed | 3 | 1,140 | 17.014 |
| 2026-11-21 20:36:45 | DataHub | Memory guard reduced workers | 3 → 2 | 1,281 | 4.76 |
| 2026-11-21 20:36:57 | DataHub | Resumed | 2 | 1,281 | 10.065 |
| 2026-11-21 20:37:54 | DataHub | Memory guard reduced workers | 2 → 1 | 1,281 | 4.992 |
| 2026-11-21 20:37:55 | DataHub | Resumed | 1 | 1,281 | 6.839 |
| 2026-11-21 22:30:18 | DataHub | Operator requested four workers | 1 | 4,982 | 6.657 |
| 2026-11-21 22:30:19 | DataHub | Old process tree stopped | 1 → 0 | 4,982 | 10.535 |
| 2026-11-21 22:30:22 | DataHub | Operator requested a four-worker resume | 4 | 4,982 | 10.449 |
| 2026-11-21 22:30:30 | DataHub | Resumed | 4 | 4,982 | 10.637 |
| 2026-11-21 22:32:27 | DataHub | Memory guard reduced workers | 4 → 3 | 4,983 | 4.997 |
| 2026-11-21 22:32:31 | DataHub | Resumed | 3 | 4,983 | 10.621 |
| 2026-11-21 22:35:51 | DataHub | Memory guard reduced workers | 3 → 2 | 4,989 | 4.993 |
| 2026-11-21 22:35:55 | DataHub | Resumed | 2 | 4,989 | 10.577 |
| 2026-11-22 00:12:49 | DataHub | Memory guard reduced workers | 2 → 1 | 5,275 | 4.989 |
| 2026-11-22 00:12:59 | DataHub | Resumed | 1 | 5,275 | 8.361 |
| 2026-11-22 00:13:06 | DataHub | Operator requested a clean stop | 1 | 5,275 | — |
| 2026-11-22 00:18:23 | DataHub | Clean stop blocked. Run left active. | 1 | 5,276 | — |
| 2026-11-22 01:51:00 | DataHub | Operator requested a forced stop to change workers | 1 | 5,327 | 13.276 |
| 2026-11-22 01:51:00 | DataHub | Old process tree stopped | 0 | 5,327 | 14.87 |
| 2026-11-22 01:51:06 | DataHub | Checkpoint and frozen inputs verified | 0 | 5,327 | — |
| 2026-11-22 01:51:06 | DataHub | Operator requested a four-worker resume | 4 | 5,327 | 15.01 |
| 2026-11-22 01:51:15 | DataHub | Resumed | 4 | 5,327 | 15.016 |
| 2026-11-22 01:52:40 | DataHub | Resume verified. Completed calls skipped. | 4 | 5,327 | — |
| 2026-11-22 07:14:52 | DataHub | Completed | 4 → 0 | 6,780 | 14.936 |

The clean-stop request was logged with the earlier two-worker reading. The supervisor had already reduced the run to one worker at 00:12:49 IST.
