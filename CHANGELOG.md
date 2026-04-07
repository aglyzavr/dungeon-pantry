# Changelog

## [Unreleased]

### Fixed

- **#38** — `start.sh`: removed misleading comment; `set -e` already ensures the script exits on error
- **#37** — DB pool size and max overflow are now configurable via `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` env vars (defaults: 10 / 5)
- **#35** — Added `aria-label` to all icon-only interactive elements (close ✕, inspiration ⭐, death-save dots, shield toggle, portrait upload, edit ✏️, quantity ±)
- **#34** — Portrait upload modal and notes modal now include `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, ESC key handler, and focus trap/restore
- **#30** — DB credentials are now URL-encoded with `urllib.parse.quote_plus` in `database_url`
- **#26** — `ShareLinkRepository.revoke()` and `delete()` now use single-query `UPDATE`/`DELETE` instead of SELECT-then-mutate
- **#25** — `CharacterRepository` exposes public `flush()` and `update_owner()` methods; removed all `_repo._db` accesses from the service layer
- **#23** — Caster-class detection uses exact set membership (`class_lower in {set}`) instead of substring matching to prevent false positives
- **#19** — DB session rollback now logs the exception with `exc_info=True` before re-raising
- **#16** — `campaign_handler`: replaced silent `except … pass` with `logger.warning()` calls
- **#13** — `create_player()` catches `IntegrityError` after `flush()` to close the TOCTOU race on duplicate usernames
