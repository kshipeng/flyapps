#!/usr/bin/env python
# -*- coding:utf-8 -*-
# project: 4月
# author: liuyu
# date: 2020/4/7

from django.core.cache import cache
from api.models import Apps,UserInfo
import time
from fir_ser.settings import CACHE_KEY_TEMPLATE
from api.utils.storage.storage import Storage,LocalStorage
from api.utils.crontab import run

def get_download_url_by_cache(app_obj, filename, limit, isdownload=True):
    now = time.time()
    if isdownload is None:
        local_storage = LocalStorage('localhost', False)
        return local_storage.get_download_url(filename, limit, 'plist')
    download_val = cache.get("%s_%s" % ('download_url', filename))
    if download_val:
        if download_val.get("time") > now - 60:
            return download_val.get("download_url")
    else:
        user_obj = UserInfo.objects.filter(pk=app_obj.get("user_id")).first()
        storage = Storage(user_obj)
        return storage.get_download_url(filename, limit)


def get_app_instance_by_cache(app_id, limit):
    app_key="_".join([CACHE_KEY_TEMPLATE.get("app_instance_key"),app_id])
    app_obj_cache = cache.get(app_key)
    if not app_obj_cache:
        app_obj_cache = Apps.objects.filter(app_id=app_id).values("pk", 'user_id', 'type').first()
        cache.set(app_key, app_obj_cache, limit)
    return app_obj_cache


def get_app_download_by_cache(app_id):
    down_tem_key = "_".join([CACHE_KEY_TEMPLATE.get("download_times_key"),app_id])
    download_times = cache.get(down_tem_key)
    if not download_times:
        download_times=Apps.objects.filter(app_id=app_id).values("count_hits").first().get('count_hits')
        cache.set(down_tem_key, download_times + 1, 900)
    else:
        cache.incr(down_tem_key)
    return download_times + 1

def del_cache_response_by_short(short,app_id):
    cache.delete("_".join([CACHE_KEY_TEMPLATE.get("download_short_key"),short]))
    cache.delete("_".join([CACHE_KEY_TEMPLATE.get("app_instance_key"),app_id]))
