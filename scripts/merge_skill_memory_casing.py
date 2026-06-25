"""One-time migration: fold case-variant skill_memory keys into one entry.

The novelty fix (storage/skills._norm_skill_key) stops NEW case splits, but data
written before it still has the same topic under several keys — e.g. LangChain as
"Langchain" (Jun 7, 15), "LangChain" (Jun 8, 21) and "langchain" (Jun 19). With
the history fragmented, each variant carries a low times_taught, so spaced
repetition can't widen the interval and the radar re-teaches it ~weekly.

This merges every group of keys that share _norm_skill_key into a single entry:
  - display key  = the variant whose first lesson is earliest (the original name)
  - lessons      = all variants' lessons, deduped by date, sorted ascending
  - times_taught = number of merged lessons (the real teaching count)
  - first/last_taught, summary = derived from the merged, date-sorted lessons

Reads/writes skill_memory.json under STATE_DIR (defaults to the storage package
dir; point it at the private state checkout to migrate the real file):

  STATE_DIR=../_state_tmp python -m scripts.merge_skill_memory_casing          # dry run
  STATE_DIR=../_state_tmp python -m scripts.merge_skill_memory_casing --apply  # write
"""
import sys

from storage import paths
from storage.skills import _norm_skill_key, load_memory, save_memory


def _earliest_lesson_date(entry: dict) -> str:
    dates = [le.get("date", "") for le in entry.get("lessons", []) if le.get("date")]
    return min(dates) if dates else (entry.get("first_taught") or "9999-12-31")


def merge_casing(skills: dict) -> tuple[dict, list[tuple[list[str], str]]]:
    """Return (new_skills, merges) where merges lists ([variant_keys], kept_key)."""
    groups: dict[str, list[str]] = {}
    for key in skills:
        groups.setdefault(_norm_skill_key(key), []).append(key)

    new_skills: dict = {}
    merges: list[tuple[list[str], str]] = []
    for keys in groups.values():
        if len(keys) == 1:
            new_skills[keys[0]] = skills[keys[0]]
            continue
        # Keep the name whose earliest lesson is oldest — the topic's original form.
        kept = min(keys, key=lambda k: _earliest_lesson_date(skills[k]))
        lessons_by_date: dict[str, dict] = {}
        for k in keys:
            for le in skills[k].get("lessons", []):
                d = le.get("date", "")
                lessons_by_date.setdefault(d, le)  # first variant wins a same-date clash
        lessons = [lessons_by_date[d] for d in sorted(lessons_by_date)]
        merged = dict(skills[kept])
        merged["lessons"] = lessons
        merged["times_taught"] = len(lessons)
        merged["first_taught"] = lessons[0].get("date") if lessons else merged.get("first_taught")
        merged["last_taught"] = lessons[-1].get("date") if lessons else merged.get("last_taught")
        merged["summary"] = lessons[-1].get("summary", "") if lessons else merged.get("summary", "")
        new_skills[kept] = merged
        merges.append((keys, kept))
    return new_skills, merges


def main() -> int:
    apply = "--apply" in sys.argv
    memory = load_memory()
    skills = memory.get("skills", {})
    new_skills, merges = merge_casing(skills)

    if not merges:
        print(f"No case-variant duplicates in {paths.MEMORY_FILE}. Nothing to do.")
        return 0

    print(f"skill_memory: {paths.MEMORY_FILE}")
    for keys, kept in merges:
        total = new_skills[kept]["times_taught"]
        print(f"  merge {keys} -> '{kept}'  (times_taught now {total})")

    if not apply:
        print("\nDry run. Re-run with --apply to write.")
        return 0

    memory["skills"] = new_skills
    save_memory(memory)
    print(f"\nWrote {paths.MEMORY_FILE} ({len(new_skills)} skills).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
