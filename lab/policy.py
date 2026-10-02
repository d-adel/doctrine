from dataclasses import dataclass

CLASSES = ("background", "sweep", "experiment", "milestone", "gate")
AGING_STEP = 10


@dataclass(frozen=True)
class Job:
    id: int
    cls: str
    needs: frozenset = frozenset()
    waiting: bool = False
    short: bool = False
    overtaken: int = 0


def rank(job, aging_step=AGING_STEP):
    base = CLASSES.index(job.cls)
    boost = 1 if job.waiting and job.short else 0
    aged = max(base, min(base + job.overtaken // aging_step, len(CLASSES) - 2))
    return min(aged + boost, len(CLASSES) - 1)


def eligible(job, labels):
    return job.needs <= frozenset(labels)


def pick(queue, labels, aging_step=AGING_STEP):
    candidates = [job for job in queue if eligible(job, labels)]
    if not candidates:
        return None
    return max(candidates, key=lambda job: (rank(job, aging_step), -job.id))


def passed_over(queue, labels, chosen):
    return [job.id for job in queue if job.id < chosen.id and eligible(job, labels)]
