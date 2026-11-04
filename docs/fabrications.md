# Subagent Fabrication Log

Records every subagent claim that failed verification.

| Date | Claim | Failure |
|------|-------|---------|
| 2026-10-20 16:51:47 | --file-exists /tmp/nonexistent.py | FABRICATED: /tmp/nonexistent.py does not exist |
| 2026-10-20 16:51:49 | --command "false" | FABRICATED: command exited 1:  |
| 2026-10-20 16:51:50 | --file-exists /tmp/nonexistent_12345.py | FABRICATED: /tmp/nonexistent_12345.py does not exist |
| 2026-10-20 16:51:50 | --file-contains /tmp/pytest-of-d.scasciafratte/pytest-2/test_file_contains_false0/test.py 'def main' | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-2/test_file_contains_false0/test.py does not contain "def main" |
| 2026-10-20 16:51:50 | --command "false" | FABRICATED: command exited 1:  |
| 2026-10-20 16:51:50 | --file-exists /tmp/pytest-of-d.scasciafratte/pytest-2/test_empty_file_is_fabricated0/empty.py | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-2/test_empty_file_is_fabricated0/empty.py exists but is empty (0 bytes) |
| 2026-10-20 16:51:50 | --file-size /tmp/pytest-of-d.scasciafratte/pytest-2/test_file_size_below_min0/size_test.txt --min 500 --max 2000 | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-2/test_file_size_below_min0/size_test.txt is 100 bytes (below minimum 500) |
| 2026-10-20 16:51:50 | --file-size /tmp/pytest-of-d.scasciafratte/pytest-2/test_file_size_above_max0/size_test.txt --min 500 --max 2000 | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-2/test_file_size_above_max0/size_test.txt is 5000 bytes (above maximum 2000) |
| 2026-10-20 16:51:50 | --golden /tmp/pytest-of-d.scasciafratte/pytest-2/test_golden_invalid_segfault_a0/broken_golden.png | FABRICATED: golden /tmp/pytest-of-d.scasciafratte/pytest-2/test_golden_invalid_segfault_a0/broken_golden.png is 33 bytes (segfault artifact) |
| 2026-10-20 16:51:50 | --file-contains /tmp/does_not_exist_12345.py 'test' | FABRICATED: /tmp/does_not_exist_12345.py does not exist |
| 2026-10-20 16:52:05 | --file-exists /tmp/nonexistent.py | FABRICATED: /tmp/nonexistent.py does not exist |
| 2026-10-20 16:52:07 | --command "false" | FABRICATED: command exited 1:  |
| 2026-10-20 16:52:08 | --file-exists /tmp/nonexistent_12345.py | FABRICATED: /tmp/nonexistent_12345.py does not exist |
| 2026-10-20 16:52:08 | --file-contains /tmp/pytest-of-d.scasciafratte/pytest-3/test_file_contains_false0/test.py 'def main' | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-3/test_file_contains_false0/test.py does not contain "def main" |
| 2026-10-20 16:52:08 | --command "false" | FABRICATED: command exited 1:  |
| 2026-10-20 16:52:08 | --file-exists /tmp/pytest-of-d.scasciafratte/pytest-3/test_empty_file_is_fabricated0/empty.py | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-3/test_empty_file_is_fabricated0/empty.py exists but is empty (0 bytes) |
| 2026-10-20 16:52:08 | --file-size /tmp/pytest-of-d.scasciafratte/pytest-3/test_file_size_below_min0/size_test.txt --min 500 --max 2000 | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-3/test_file_size_below_min0/size_test.txt is 100 bytes (below minimum 500) |
| 2026-10-20 16:52:08 | --file-size /tmp/pytest-of-d.scasciafratte/pytest-3/test_file_size_above_max0/size_test.txt --min 500 --max 2000 | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-3/test_file_size_above_max0/size_test.txt is 5000 bytes (above maximum 2000) |
| 2026-10-20 16:52:08 | --golden /tmp/pytest-of-d.scasciafratte/pytest-3/test_golden_invalid_segfault_a0/broken_golden.png | FABRICATED: golden /tmp/pytest-of-d.scasciafratte/pytest-3/test_golden_invalid_segfault_a0/broken_golden.png is 33 bytes (segfault artifact) |
| 2026-10-20 16:52:08 | --file-contains /tmp/does_not_exist_12345.py 'test' | FABRICATED: /tmp/does_not_exist_12345.py does not exist |
| 2026-10-20 16:54:00 | --file-exists /tmp/nonexistent.py | FABRICATED: /tmp/nonexistent.py does not exist |
| 2026-10-20 16:54:37 | --file-exists /tmp/nonexistent_12345.py | FABRICATED: /tmp/nonexistent_12345.py does not exist |
| 2026-10-20 16:54:37 | --file-contains /tmp/pytest-of-d.scasciafratte/pytest-5/test_file_contains_false0/test.py 'def main' | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-5/test_file_contains_false0/test.py does not contain "def main" |
| 2026-10-20 16:54:37 | --command "false" | FABRICATED: command exited 1:  |
| 2026-10-20 16:54:37 | --file-exists /tmp/pytest-of-d.scasciafratte/pytest-5/test_empty_file_is_fabricated0/empty.py | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-5/test_empty_file_is_fabricated0/empty.py exists but is empty (0 bytes) |
| 2026-10-20 16:54:37 | --file-size /tmp/pytest-of-d.scasciafratte/pytest-5/test_file_size_below_min0/size_test.txt --min 500 --max 2000 | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-5/test_file_size_below_min0/size_test.txt is 100 bytes (below minimum 500) |
| 2026-10-20 16:54:37 | --file-size /tmp/pytest-of-d.scasciafratte/pytest-5/test_file_size_above_max0/size_test.txt --min 500 --max 2000 | FABRICATED: /tmp/pytest-of-d.scasciafratte/pytest-5/test_file_size_above_max0/size_test.txt is 5000 bytes (above maximum 2000) |
| 2026-10-20 16:54:38 | --golden /tmp/pytest-of-d.scasciafratte/pytest-5/test_golden_invalid_segfault_a0/broken_golden.png | FABRICATED: golden /tmp/pytest-of-d.scasciafratte/pytest-5/test_golden_invalid_segfault_a0/broken_golden.png is 33 bytes (segfault artifact) |
| 2026-10-20 16:54:38 | --file-contains /tmp/does_not_exist_12345.py 'test' | FABRICATED: /tmp/does_not_exist_12345.py does not exist |
