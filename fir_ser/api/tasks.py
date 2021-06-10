#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project: 5月 
# author: NinEveN
# date: 2021/5/27

from celery import shared_task
from django.core.cache import cache
from celery import Celery

from api.utils.storage.storage import get_local_storage

from api.models import Apps
from api.utils.app.supersignutils import IosUtils, resign_by_app_id
from api.utils.crontab.ctasks import sync_download_times, auto_clean_upload_tmp_file, auto_delete_tmp_file, \
    auto_check_ios_developer_active
from api.utils.geetest.geetest_utils import check_bypass_status

app = Celery()


@shared_task
def run_sign_task(format_udid_info, short):
    app_info = Apps.objects.filter(short=short).first()
    with cache.lock("%s_%s_%s" % ('task_sign', app_info.app_id, format_udid_info.get('udid')), timeout=60 * 10):
        ios_obj = IosUtils(format_udid_info, app_info.user_id, app_info)
        status, msg = ios_obj.sign()
        if not status:
            code = msg.get("code", -1)
            if code == 0:
                msg = ""
            elif code == 1005:
                msg = "签名余额不足"
            elif code == 1002:
                msg = "维护中"
            elif code == 1003:
                msg = "应用余额不足"
            elif code in [1004, 1001, 1009]:
                msg = msg.get('msg', '未知错误')
            else:
                msg = '系统内部错误'
        else:
            msg = ""
        return msg


@shared_task
def run_resign_task(app_id, need_download_profile=True):
    app_obj = Apps.objects.filter(app_id=app_id).first()
    with cache.lock("%s_%s" % ('task_resign', app_id), timeout=60 * 60):
        return resign_by_app_id(app_obj, need_download_profile)


@app.task
def start_api_sever_do_clean():
    # 启动服务的时候，同时执行下面操作,主要是修改配置存储的时候，需要执行清理，否则会出问题，如果不修改，则无需执行
    get_local_storage(clean_cache=True)
    check_bypass_status()


@app.task
def sync_download_times_job():
    sync_download_times()


@app.task
def check_bypass_status_job():
    check_bypass_status()


@app.task
def auto_clean_upload_tmp_file_job():
    auto_clean_upload_tmp_file()


@app.task
def auto_delete_tmp_file_job():
    auto_delete_tmp_file()


@app.task
def auto_check_ios_developer_active_job():
    auto_check_ios_developer_active()