from arq import cron
from pipelines.finetuning.job_manager import poll_finetune_status

class ARQSettings:
    cron_jobs = [
        cron(poll_finetune_status, minute=0, run_every=60),  # Every minute
    ]