# P00 Baseline Drift Report

- Planning basis commit: `afc50a1e179c64321645b278b2497ea3ab3fe24d`
- Actual starting commit: `afc50a1e179c64321645b278b2497ea3ab3fe24d`
- Actual starting branch: `main`
- P00 feature branch: `codex/duraloco-p00-contract`
- Starting tree: dirty (45 tracked files modified before P00 implementation)

There is no commit drift: the checked-out commit exactly matches the planning
basis. The worktree contained pre-existing changes covering artifact retention,
Miyabi module/Python recording, documentation, configs, tests, and corrections
to the planning bundle. Those changes are preserved and treated as part of the
observed baseline; P00 does not reset or silently attribute them to a clean
commit.

`starting_orientation.log` preserves the initial host, branch, commit, and
dirty-path list observed before P00 edits. The immutable baseline manifest
hashes all critical files from the exact planning-basis Git tree. Because it
was generated later, its `git.status` is explicitly only the overlay present at
capture time; it is not represented as the initial dirty snapshot, and
untracked overlay contents are not content-hashed by that manifest.

Because the pre-existing changes alter legacy runtime configuration/retention,
P00-A06 is interpreted as “P00's DuraLoCo contract/protocol/reference additions
do not further change the legacy runtime defaults.” Compatibility tests bind
that boundary, while the pre-existing delta remains explicitly visible in Git
history and this report.
