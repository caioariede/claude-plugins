# Versioning

Every skill carries its own version in its `SKILL.md` `metadata.version`.
A plugin's version is derived from those: it bumps the same position as
the highest-severity skill bump in the release.

## Bumping a skill

Bump the changed skill's version honestly.

| Change | Bump |
| --- | --- |
| Wording, formatting, a clarification that does not change behavior | patch |
| New behavior, a new option, a new output line | minor |
| A contract change that breaks existing callers | major |

Only `version:` fields in `SKILL.md` move the plugin version. Changing
`hooks/`, `tests/`, or the `Justfile` moves nothing on its own; if the
change is user-visible, bump the owning skill.

## Bumping the plugin

Never edit `plugin.json`'s version by hand. Run:

```bash
cd plugins/<plugin> && just bump-plugin-version
```

That reads `.claude-plugin/skill-versions.json`, a tracked snapshot of
every skill's version as of the current plugin version, compares it
against the live `SKILL.md` versions, and applies the highest severity:

```
severity(old -> new):   major   if major differs
                        minor   if minor differs
                        patch   if patch differs
                        none    otherwise

        skill added  -> minor
        skill gone   -> major
        new < old    -> hard error (versions are monotonic)

overall = max(severity across all skills)
          ordered  major > minor > patch > none

plugin bump:  major -> (M+1, 0,   0)
              minor -> (M,   m+1, 0)
              patch -> (M,   m,   p+1)
              none  -> unchanged
```

Worked example:

```
skills/ws-next/SKILL.md   0.9.0  -> 0.10.0   minor
skills/ws-board/SKILL.md  0.5.4  -> 0.5.5    patch
skills/ws/SKILL.md        0.15.0 -> 0.15.0   none
overall = minor
plugin  0.15.0 -> 0.16.0
```

The plugin version is its own counter, not `max()` of the skill
versions. It will drift away from any individual skill's version.

Run `bump-plugin-version` once, last, before finalizing. It is a no-op
when no skill version moved, so a stray second run is harmless, but
interleaving skill edits with runs accumulates increments: a minor
followed later by a patch lands at `0.16.1` rather than `0.16.0`. That
never under-signals severity, so it is cosmetic.

## Promoting deliberately

The check demands an exact match, so a promotion that the rule would not
produce needs the escape hatch. It writes `plugin.json` and the
snapshot's `plugin` key together:

```bash
cd plugins/<plugin> && just set-plugin-version version=1.0.0
```

## The guide stamp

`WORKSTREAMS-GUIDE.html` stamps full semver `X.Y.Z` to match
`plugin.json`. Patch bumps require updating the HTML stamp; run
`just gen-guide-pdf` when shipping the PDF:

```bash
cd plugins/workstreams && just gen-guide-pdf
```

## CI

`.github/workflows/workstreams-version.yml` runs the version and guide
checks, calling `tools/plugin_version.py` directly so the logic lives in
exactly one place. `.github/workflows/workstreams-tests.yml` runs the
engine suites on any change under `skills/`, `hooks/`, or `tests/`.

`just check` runs everything both workflows do.
