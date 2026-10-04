# Validation scope

## Initial release, 2026-10-04

The release is a documentation and agent-instruction bundle. Structural checks
cover the eight skill entry points, UI metadata, local-reference reachability,
and the mapping of the 33 reviewed official sidebar entries.

The built-in skill-creator validator is also run against each entry point during
authoring. Repository CI reruns the portable structural checks.

Online validation checks source availability and compares the live official
sidebar with the recorded inventory. It cannot detect every semantic change to
a page; maintainers must read changed guidance before refreshing review dates.

## Observed authoring checks

- Built-in skill-creator validation: 8 of 8 entry points passed.
- Repository validation: 8 skills, 22 reachable references, 33 source mappings.
- Online validation: 36 official URLs checked; live sidebar matched the inventory.
- Negative fixtures: missing reference, wrong invocation metadata, missing source
  entry, and a link outside the bundle were all rejected. Fixtures were removed.
- Public-content review found no private workspace paths or known credential markers.
- Git whitespace validation passed.

CI status belongs to the exact commit and must be read from GitHub; these local
checks do not substitute for it.

## Behavioral evaluation

The layout recipes and interaction scenarios contain expected reasoning for
manual or independent agent evaluation. Their presence is not an executed test.

This initial release has not been validated by a separate agent executing those
tasks, nor by building an Android app. No emulator, physical device, TalkBack,
Credential Manager, notification, PiP, widget host, or cross-harness installation
acceptance is claimed.

When evaluating a skill, give the agent a realistic request and the minimum
relevant artifacts. Judge its observable decisions against user intent,
platform constraints, scope, and evidence. Record the actual result separately
from these suggested exercises.
