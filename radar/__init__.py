"""The radar: turn raw source items into a single teaching brief.

Pipeline (called in order from main.py):

    skill_extractor.extract(items)        -> list[SkillMention]
    gap_scorer.score(mentions, memory)    -> list[ScoredSkill]  (ranked)
    brief_writer.write(top_skill, ...)    -> markdown brief (str)

The brief is the hand-off point to the learnx audio pipeline.
"""
