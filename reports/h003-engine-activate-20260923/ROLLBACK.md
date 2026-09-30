# Retained rollback — not executed

Private host snapshot: `/home/user/.local/share/ai-harness-deploy/H003-HARNESS-ENGINE-ACTIVATE-20260923/rollback-20260923T131930Z`. It retains the prior release/unit/config, engine identity, all data directories and consistent final `harness-final-idle.sqlite` (integrity ok; SHA256 `c1cb3aa579c569c4e7534352ec09fa042f2196105af10a88e8e47c3d9669b73a`). Raw data and credentials are not published.

Prior source: `/home/user/.local/share/ai-harness-app/releases/b5717d03416252c8640c47d37baf892a0c4e532a`. Prior engine ID: `31b7a4d0aba256266e55a4aa510b0b7af484bef3502e9ffa2b333cf6c48b1428`; digest `sha256:617c01955ccf794ea6642af64a5ac1800df00a8be9adf0d07679b42fc4679453`. Prior unit SHA256 `f8cf9f43a0e80ad818ee250370fb95a2693436794f55611c267c88ef21533cb5`; launcher SHA256 `a8bba22b347f1eee0acb36a77627b04787994096a919f9ac0c8140e88d2ef4b2`. Production alias: `localhost/ai-harness-engine:0.0.2-ae65651df5f9`.

Only a separately authorized lifecycle owner may roll back after acceptance ownership returns and all user work/text lanes/nonterminal image jobs are idle. First retain fresh consistent data; stop gracefully and verify exit0. While stopped, restore the backed-up unit and prior immutable image alias together; validate/reload the unit, start once and verify the exact pair, HTTP80 and preserved state. No nginx/key/model/imageAPI changes or pruning.

Keep the current application DB and newer files by default. Never overwrite newer chats with the old snapshot or restore `owner.sqlite` (process lock). Any data restore requires separately assessed loss scope. No rollback or host contact occurred in this docs-only trim.
