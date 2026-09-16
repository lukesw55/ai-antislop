## Goal

<!-- What this change is for, in one or two sentences. -->

## Changes

<!-- What changed, grouped by area. -->

## Verification

<!-- The exact commands you ran and what they reported. Not "tests pass". -->

```
python -m unittest discover tests
python anti-slop/scripts/scan_repo_slop.py . --fail-on-block --fail-on-incomplete --summary
python anti-slop/hooks/anti-slop-stop.py --check
```

## Limitations

<!-- What you could not validate, and why. -->

## Base

- [ ] This pull request targets `main`.

If it targets another pull request's branch instead, do not merge it as is. Once the
parent merges, retarget this one to `main`, re-read the diff against `main`, let CI run
again, and only then merge. A stacked pull request merged into its parent's branch does
not reach `main`.
