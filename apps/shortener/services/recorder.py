"""把访问记录放到后台线程执行，保证 302 跳转接口极低延迟、不被统计写库拖慢。

说明：访问日志属于「可异步、允许极小概率丢失」的旁路操作，使用守护线程即可满足
单机 / 演示场景；在高并发生产环境下，可平滑替换为 Celery + 消息队列（接口不变）。
注意：Django 的数据库连接是线程局部的，线程结束时必须显式关闭。
"""
import threading


def record_access_async(*, short_url_id: int, code: str, ip: str,
                        user_agent: str, referer: str) -> None:
    def _job():
        from django.db import connection
        try:
            from shortener.services import stats
            stats.record_access(
                short_url_id=short_url_id, code=code, ip=ip,
                user_agent=user_agent, referer=referer,
            )
        except Exception:
            # 统计失败不影响跳转主流程
            pass
        finally:
            connection.close()

    threading.Thread(target=_job, daemon=True).start()
