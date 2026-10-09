from celery import shared_task

from examleaf.celery import single_run


@shared_task
@single_run(300)
def publish_due():
    """Nightly, just after midnight in India (celery beat): each legal page's version published for a later day is put
    in force once its day comes (pages.versions.publish_due). Run twice, the second finds nothing waiting."""
    from .versions import publish_due as put_in_force

    return put_in_force()
